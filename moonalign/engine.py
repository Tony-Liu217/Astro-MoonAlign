"""Batch rigid registration engine for full-disc RGB16 lunar TIFF sequences.

Only source pixel rotation/translation is applied; files are opened read-only.
Public API: inspect_files() and run_alignment(). No GUI or CLI dependencies.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import ctypes
import csv
import hashlib
import io
import json
import math
import msvcrt
import os
from pathlib import Path
import shutil
import struct
import sys
import time
import traceback
import threading
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image

ALGORITHM_VERSION = '2.0.0-gui'
VERSION = ALGORITHM_VERSION
PARAMETERS = {
    'version': VERSION, 'model': 'rigid_rotation_translation_scale_1',
    'sift_features': 5000, 'sift_ratio': .72, 'ransac_px': 1.5,
    'minimum_fit_inliers': 150, 'maximum_fit_median_px': 1.0,
    'minimum_holdout_points': 40, 'minimum_holdout_consistency': .7,
    'maximum_holdout_median_px': 1.25, 'maximum_diagnostic_scale_deviation': .01,
    'minimum_feature_extent_px': 500,
    'minimum_lk_holdout': 25, 'maximum_lk_median_px': .9,
    'maximum_lk_p90_px': 1.6, 'maximum_remaining_angle_deg': .06,
    'maximum_remaining_center_shift_px': .6,
    'resampling': 'OpenCV INTER_CUBIC once on original UInt16 RGB',
    'lk_refinement': 'accept only if held-out median, p90, angle and shift do not degrade',
    'output': 'uncompressed_baseline_chunky_RGB_UInt16_TIFF_source_ICC_only',
}
# OpenCV's thread count is process-global. Only a running alignment owns this
# lock; importing the library never changes settings used by another component.
_COMPUTE_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _cpu_resources():
    logical, physical = max(1, os.cpu_count() or 1), None
    if os.name == 'nt':
        try:
            class ProcessorInfo(ctypes.Structure):
                _fields_ = [('mask', ctypes.c_size_t), ('relationship', ctypes.c_ulong),
                            ('reserved', ctypes.c_ulonglong * 2)]
            size = ctypes.c_ulong()
            query = ctypes.windll.kernel32.GetLogicalProcessorInformation
            query(None, ctypes.byref(size))
            if size.value and size.value % ctypes.sizeof(ProcessorInfo) == 0:
                data = ctypes.create_string_buffer(size.value)
                if query(data, ctypes.byref(size)):
                    array = ctypes.cast(data, ctypes.POINTER(ProcessorInfo))
                    physical = sum(array[i].relationship == 0
                                   for i in range(size.value // ctypes.sizeof(ProcessorInfo))) or None
            # Respect an explicitly restricted process affinity when available.
            process_mask, system_mask = ctypes.c_size_t(), ctypes.c_size_t()
            affinity = ctypes.windll.kernel32.GetProcessAffinityMask
            affinity.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
            if affinity(ctypes.c_void_p(-1), ctypes.byref(process_mask), ctypes.byref(system_mask)):
                logical = min(logical, process_mask.value.bit_count()) or logical
        except (OSError, AttributeError, ValueError):
            pass
    return logical, min(physical, logical) if physical else None


def _memory_resources():
    if os.name == 'nt':
        try:
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total',
                    'page_available', 'virtual_total', 'virtual_available', 'extended')]
            info = MemoryStatus()
            info.length = ctypes.sizeof(info)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
                return int(info.total), int(info.available)
        except (OSError, AttributeError):
            pass
    # Conservative fallback rather than claiming the whole machine is available.
    return 8 * 1024**3, 4 * 1024**3


def get_performance_profile(dimensions=None, mode='balanced', workers=None, compute_threads=None,
                            memory_policy='conservative'):
    """Choose bounded resources only; all four modes use identical quality gates.

    dimensions is [width, height], or None for the measured 1800x1800 baseline.
    Custom worker/compute settings must fit both logical CPUs and available RAM.
    Both memory policies retain a bounded reserve. Expanded is an explicit
    advanced opt-in; estimates are not promises about other applications.
    """
    if mode not in ('quiet', 'balanced', 'performance', 'custom'):
        raise ValueError('未知性能模式')
    if memory_policy not in ('conservative', 'expanded'):
        raise ValueError('未知内存策略，应为 conservative 或 expanded')
    if dimensions is None:
        dimensions = (1800, 1800)
    if len(dimensions) != 2 or any(int(value) <= 0 for value in dimensions):
        raise ValueError('性能估算需要有效的图片宽度和高度')
    pixels = int(dimensions[0]) * int(dimensions[1])
    logical, physical = _cpu_resources()
    total, available = _memory_resources()
    automatic_threads = 2 if mode in ('balanced', 'performance') and logical >= 4 else 1
    threads = int(compute_threads if mode == 'custom' and compute_threads is not None else automatic_threads)
    if not 1 <= threads <= min(8, logical):
        raise ValueError(f'每项计算线程应为 1～{min(8, logical)}')
    # Measured Windows/OpenCV peaks were ~0.8 GiB per simultaneous 1800² SIFT
    # frame. The per-worker estimate is unchanged by the advanced policy; only
    # the reserved RAM differs. CPU and RAM limits always remain in force.
    per_worker = max(256 * 1024**2, int(pixels * 300))
    overhead = 384 * 1024**2 + pixels * 40
    reserve = (max(3 * 1024**3, int(available * .25)) if memory_policy == 'conservative'
               else max(1024**3, int(available * .10)))
    memory_workers = max(0, (available - reserve - overhead) // per_worker)
    # With RAM limiting simultaneous pictures, 3x4 was faster than 3x2 on the
    # 20-thread validation machine at the same ~2.9 GiB peak private memory.
    # Raise inner parallelism only when it fits without reducing photo workers.
    if mode == 'performance' and threads == 2 and 1 <= memory_workers <= logical // 4:
        threads = 4
    maximum = max(1, min(32, logical // threads, int(memory_workers)))
    requested = {'quiet': max(1, logical // 5), 'balanced': max(1, logical * 3 // 10),
                 'performance': max(1, logical // threads), 'custom': 3}[mode]
    if mode == 'custom' and workers is not None:
        requested = int(workers)
        if not 1 <= requested <= maximum:
            raise ValueError(f'当前 CPU/可用内存下并行数量应为 1～{maximum}')
    chosen = min(maximum, requested)
    estimated = int(overhead + chosen * per_worker)
    sufficient = bool(memory_workers >= 1)
    note = '所有模式保留相同配准精度和完整校验；更高并发不保证更快。'
    if chosen < requested:
        note += ' 已按当前 CPU/可用内存限制并发。'
    if mode == 'performance' and threads == 4:
        note += ' 内存限制并发时，使用更多计算线程。'
    if memory_policy == 'expanded':
        note += ' 已放宽内存限制：预留至少 1 GiB，且不少于当前可用内存的 10%；可能增加换页、卡顿或内存不足的风险。'
    if not sufficient:
        note += ' 当前可用内存偏低，开始前请关闭占用内存的程序。'
    return {'mode': mode, 'workers': chosen, 'compute_threads': threads,
            'max_workers': maximum, 'max_compute_threads': min(8, logical),
            'estimated_memory_bytes': estimated,
            'available_memory_bytes': available, 'total_memory_bytes': total,
            'logical_cpus': logical, 'physical_cores': physical,
            'memory_sufficient': sufficient, 'memory_per_worker_bytes': per_worker,
            'memory_policy': memory_policy, 'reserved_memory_bytes': reserve,
            'memory_budget_bytes': max(0, available - reserve),
            'note': note}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, obj):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def read_rgb_bytes(data):
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if bgr is None or bgr.dtype != np.uint16 or bgr.ndim != 3 or bgr.shape[2] != 3:
        raise ValueError('Input must decode as three-channel UInt16 RGB TIFF')
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def metadata(data):
    with Image.open(io.BytesIO(data)) as image:
        tags = image.tag_v2
        return {'size': list(image.size), 'bits': list(tags.get(258, ())),
                'channels': int(tags.get(277, 0)), 'compression': int(tags.get(259, 0)),
                'photometric': int(tags.get(262, 0)),
                'orientation': int(tags.get(274, 1)),
                'icc': image.info.get('icc_profile', b'') or b''}


def gray8(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    white = max(float(np.percentile(gray, 99.8)), 1)
    return np.uint8(np.clip(gray * (230 / white), 0, 255))


def lunar_mask(gray):
    binary = np.uint8(gray > 30) * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    if count < 2:
        raise ValueError('No lunar disc detected')
    mask = np.uint8(labels == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])) * 255
    return mask


def features(gray, mask, scale=1.0):
    eroded = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (odd(81 * scale), odd(81 * scale))))
    enhanced = cv2.createCLAHE(clipLimit=2, tileGridSize=(12, 12)).apply(gray)
    detector = cv2.SIFT_create(nfeatures=5000, contrastThreshold=.012, edgeThreshold=15)
    kp, descriptors = detector.detectAndCompute(enhanced, eroded)
    if descriptors is None or len(kp) < 100:
        raise ValueError('Too few lunar texture features')
    return kp, descriptors


def rigid(a, b):
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    ca, cb = a.mean(0), b.mean(0)
    u, _, vt = np.linalg.svd((a - ca).T @ (b - cb))
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1] *= -1
        rotation = vt.T @ u.T
    return np.column_stack((rotation, cb - rotation @ ca))


def transform(points, matrix):
    return np.asarray(points) @ matrix[:, :2].T + matrix[:, 2]


def compose(a, b):
    return (np.vstack((a, [0, 0, 1])) @ np.vstack((b, [0, 0, 1])))[:2]


def angle(matrix):
    return math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))


def point_coverage(points, center):
    p = np.asarray(points)
    quadrants = set(((p[:, 0] >= center[0]).astype(int) +
                     2 * (p[:, 1] >= center[1]).astype(int)).tolist())
    return {'extent_px': np.ptp(p, axis=0).tolist(), 'quadrants': len(quadrants)}


def choose_lk_points(gray, mask, scale=1.0):
    inner = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (odd(101 * scale), odd(101 * scale))))
    points = cv2.goodFeaturesToTrack(gray, 800, .005, max(8, int(15 * scale)), mask=inner, blockSize=7)
    if points is None:
        raise ValueError('No independent verification points')
    counts, selected = {}, []
    for p in points.reshape(-1, 2):
        cell = tuple((p // max(40, int(100 * scale))).astype(int))
        if counts.get(cell, 0) < 2:
            counts[cell] = counts.get(cell, 0) + 1
            selected.append(p)
    if len(selected) < 80:
        raise ValueError('Too few spatially distributed verification points')
    return np.float32(selected).reshape(-1, 1, 2)


def track(reference, target, points, scale=1.0):
    args = dict(winSize=(odd(41 * scale), odd(41 * scale)), maxLevel=2,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, .001))
    q, sf, _ = cv2.calcOpticalFlowPyrLK(reference, target, points, None, **args)
    if q is None:
        raise ValueError('Independent texture tracking failed')
    back, sb, _ = cv2.calcOpticalFlowPyrLK(target, reference, q, None, **args)
    if back is None:
        raise ValueError('Reverse texture tracking failed')
    fb = np.linalg.norm(back - points, axis=2).ravel()
    shift = np.linalg.norm(q - points, axis=2).ravel()
    valid = (sf.ravel() != 0) & (sb.ravel() != 0) & np.isfinite(fb) & (fb < .3 * scale) & (shift < 3 * scale)
    return q.reshape(-1, 2), valid


def summarize_tracking(points, q, valid, center):
    p = points.reshape(-1, 2)
    if int(valid.sum()) < PARAMETERS['minimum_lk_holdout']:
        raise ValueError('Too few held-out texture checks')
    error = np.linalg.norm(q[valid] - p[valid], axis=1)
    remaining = rigid(q[valid], p[valid])
    cov = point_coverage(p[valid], center)
    return {'points': int(valid.sum()), 'median_px': float(np.median(error)),
            'p90_px': float(np.percentile(error, 90)),
            'remaining_angle_deg': angle(remaining),
            'remaining_center_shift_px': float(np.linalg.norm(transform(center, remaining) - center)),
            **cov}


def write_tiff(path, rgb, icc):
    """Classic TIFF, one uncompressed chunky RGB strip, no bit-depth reduction."""
    h, w, _ = rgb.shape
    count = 12 + bool(icc)
    extra_start = 8 + 2 + count * 12 + 4
    extra = bytearray()
    def attach(data):
        if (extra_start + len(extra)) % 2:
            extra.append(0)
        offset = extra_start + len(extra)
        extra.extend(data)
        return offset
    bit_offset = attach(struct.pack('<HHH', 16, 16, 16))
    format_offset = attach(struct.pack('<HHH', 1, 1, 1))
    profile_offset = attach(icc) if icc else 0
    if (extra_start + len(extra)) % 2:
        extra.append(0)
    data_offset = extra_start + len(extra)
    raw = np.ascontiguousarray(rgb, dtype='<u2').tobytes()
    tags = [(256, 4, 1, w), (257, 4, 1, h), (258, 3, 3, bit_offset),
            (259, 3, 1, 1), (262, 3, 1, 2), (273, 4, 1, data_offset),
            (274, 3, 1, 1), (277, 3, 1, 3), (278, 4, 1, h),
            (279, 4, 1, len(raw)), (284, 3, 1, 1), (339, 3, 3, format_offset)]
    if icc:
        tags.append((34675, 7, len(icc), profile_offset))
    with path.open('wb') as stream:
        stream.write(struct.pack('<2sHIH', b'II', 42, 8, count))
        for tag in sorted(tags):
            stream.write(struct.pack('<HHII', *tag))
        stream.write(struct.pack('<I', 0))
        stream.write(extra)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def verify_written(path, expected_rgb, expected_icc):
    data = path.read_bytes()
    got = read_rgb_bytes(data)
    if not np.array_equal(got, expected_rgb):
        raise ValueError('Lossless 16-bit TIFF read-back check failed')
    md = metadata(data)
    if (md['bits'] != [16, 16, 16] or md['channels'] != 3 or md['compression'] != 1 or
        md['photometric'] != 2 or md['orientation'] != 1 or md['icc'] != expected_icc):
        raise ValueError('TIFF metadata/ICC read-back check failed')
    return {'sha256': digest(data), 'size_bytes': len(data), 'bits': md['bits'],
            'dimensions': md['size'], 'icc_bytes': len(md['icc'])}




def odd(value):
    value = max(9, int(round(value)))
    return value if value % 2 else value + 1


def _paths(files):
    result, seen, names = [], set(), {}
    for value in files:
        path = Path(value).expanduser().resolve()
        key = str(path).casefold()
        if key in seen:
            continue
        if path.suffix.lower() not in ('.tif', '.tiff') or not path.is_file():
            raise ValueError(f'不是可读取的 TIFF 文件：{path}')
        name_key = path.name.casefold()
        if name_key in names:
            raise ValueError(f'不同目录存在同名图片，无法保留原文件名：{path.name}')
        seen.add(key)
        names[name_key] = key
        result.append(path)
    return sorted(result, key=lambda p: (p.name.casefold(), str(p).casefold()))


def _file_metadata(path):
    with Image.open(path) as image:
        tags = image.tag_v2
        return {'size': list(image.size), 'bits': list(tags.get(258, ())),
                'channels': int(tags.get(277, 0)), 'compression': int(tags.get(259, 0)),
                'photometric': int(tags.get(262, 0)), 'orientation': int(tags.get(274, 1)),
                'icc': image.info.get('icc_profile', b'') or b''}


def _check_metadata(md):
    if (md['bits'] != [16, 16, 16] or md['channels'] != 3 or
            md['photometric'] != 2 or md['orientation'] != 1):
        raise ValueError('需要方向为正常、每通道 16 位的三通道 RGB TIFF；不接受灰度、8 位或带旋转方向标记的输入')
    if min(md['size']) < 800 or max(md['size']) > 6000:
        raise ValueError('目前支持每边 800～6000 像素、同尺寸的完整月盘 TIFF')


def inspect_files(files):
    """Read TIFF headers only. Recommended reference is the middle valid filename."""
    paths = _paths(files)
    valid, invalid, sizes, total_bytes = [], [], set(), 0
    for path in paths:
        try:
            md = _file_metadata(path)
            _check_metadata(md)
            sizes.add(tuple(md['size']))
            total_bytes += path.stat().st_size
            valid.append(path)
        except Exception as error:
            invalid.append({'file': str(path), 'error': str(error)})
    uniform = len(sizes) == 1
    dimensions = list(next(iter(sizes))) if uniform else None
    return {'count': len(paths), 'valid_count': len(valid), 'invalid_files': invalid,
            'uniform_dimensions': uniform, 'dimensions': dimensions,
            'total_bytes': total_bytes,
            'recommended_reference': str(valid[len(valid) // 2]) if valid else None,
            'validated_resolution': dimensions == [1800, 1800],
            'message': '要求完整近满月，月盘直径至少 800 像素（推荐 1000 以上）；尺寸相同。1800×1800 已有真实素材验证。'}


class _JobLock:
    def __init__(self, path):
        self.path, self.stream = path, None

    def __enter__(self):
        self.stream = self.path.open('a+b')
        self.stream.seek(0, 2)
        if self.stream.tell() == 0:
            self.stream.write(b'\0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.stream.close()
            raise RuntimeError('这个输出目录正在由另一个配准任务使用')
        return self

    def __exit__(self, *_):
        self.stream.seek(0)
        msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        self.stream.close()


class _Job:
    def __init__(self, files, reference, output, workers, callback, cancel_event, compute_threads=1,
                 memory_policy='conservative'):
        self.paths = _paths(files)
        if not self.paths:
            raise ValueError('没有选择图片')
        self.reference_path = Path(reference).expanduser().resolve()
        if not self.reference_path.is_file():
            raise ValueError('参考图片不存在')
        self.output = Path(output).expanduser().resolve()
        # Output must never equal or contain a selected input file or reference.
        for source in [*self.paths, self.reference_path]:
            if source == self.output or source.is_relative_to(self.output):
                raise ValueError('输出目录不能与原片目录相同，也不能是原片目录的上级目录')
        if not self.output.parent.is_dir():
            raise ValueError('输出文件夹的上级目录不存在')
        self.workers = int(workers)
        if not 1 <= self.workers <= 32:
            raise ValueError('并行数量应为 1～32，并受当前 CPU 和可用内存限制')
        self.compute_threads = int(compute_threads)
        if not 1 <= self.compute_threads <= 8:
            raise ValueError('每项计算线程应为 1～8')
        if memory_policy not in ('conservative', 'expanded'):
            raise ValueError('未知内存策略，应为 conservative 或 expanded')
        self.memory_policy = memory_policy
        self.callback = callback
        self.cancel = cancel_event or threading.Event()
        self.records = {}
        self.started = time.perf_counter()
        self.processing_seconds = 0.
        self.processing_started = None
        self.resources = None
        self.audit_done = 0
        self.pilot_passed = False
        self.stage = 'inspect'
        self.frames = self.output / 'frames'
        self.reports = self.output / 'reports'
        self.metrics = self.reports / 'per_frame'
        self.quarantine = self.output / 'quarantine'
        self.inventory = [{'path': str(p), 'name': p.name, 'size': p.stat().st_size,
                           'mtime_ns': p.stat().st_mtime_ns} for p in self.paths]
        self.inventory_by_name = {x['name']: x for x in self.inventory}

    def emit(self, event, **fields):
        counters = self.progress_counters()
        payload = {'event': event, 'stage': self.stage, 'done': len(self.records),
                   'total': len(self.paths), 'filename': '', 'status': '', 'message': '',
                   **counters, **fields}
        if self.callback is not None:
            try:
                self.callback(payload)
            except Exception:
                # A closing GUI must not interrupt an atomic image write.
                pass

    def progress_counters(self):
        now = time.perf_counter()
        new = sum(not r.get('resumed', False) for r in self.records.values())
        resumed = sum(r.get('resumed', False) for r in self.records.values())
        processing = self.processing_seconds + (now - self.processing_started
                         if self.processing_started is not None else 0.)
        speed = new / processing if new and processing > 0 else None
        remaining = max(0, len(self.paths) - len(self.records))
        eta = remaining / speed if speed and self.stage in ('pilot', 'all') and not self.cancel.is_set() else None
        return {'elapsed_seconds': now - self.started, 'processed_new': new,
                'resumed_frames': resumed, 'throughput_fps': speed, 'eta_seconds': eta,
                'workers': self.workers, 'compute_threads': self.compute_threads,
                'memory_policy': self.memory_policy,
                'reserved_memory_bytes': self.resources['reserved_memory_bytes'] if self.resources else None,
                'estimated_memory_bytes': self.resources['estimated_memory_bytes'] if self.resources else None,
                'audit_done': self.audit_done, 'audit_total': len(self.paths)}

    def initialize(self):
        self.emit('start', message='检查输入格式和参考月盘')
        inspection = inspect_files(self.paths)
        if inspection['invalid_files']:
            first = inspection['invalid_files'][0]
            raise ValueError(f"输入格式检查失败：{first['file']}；{first['error']}")
        if not inspection['uniform_dimensions']:
            raise ValueError('选择的图片尺寸不一致，请先在 PIPP 中统一裁切尺寸')
        self.resources = get_performance_profile(inspection['dimensions'], 'custom',
                                                self.workers, self.compute_threads, self.memory_policy)
        if not self.resources['memory_sufficient']:
            raise ValueError('当前可用内存不足以安全处理一张图片，请关闭占用内存的程序后重试')
        ref_data = self.reference_path.read_bytes()
        ref_md = metadata(ref_data)
        _check_metadata(ref_md)
        if ref_md['size'] != inspection['dimensions']:
            raise ValueError('参考图片尺寸与输入序列不同')
        self.reference = read_rgb_bytes(ref_data)
        self.shape = self.reference.shape
        self.height, self.width = self.shape[:2]
        self.center = np.array([self.width / 2, self.height / 2], np.float64)
        self.gray = gray8(self.reference)
        self.mask = lunar_mask(self.gray)
        disc_pixels = int(np.count_nonzero(self.mask))
        self.disc_diameter = 2 * math.sqrt(disc_pixels / math.pi)
        if self.disc_diameter < 800:
            raise ValueError(f'参考月盘直径约 {self.disc_diameter:.0f} 像素；至少需要 800 像素，推荐 1000 以上')
        ys, xs = np.nonzero(self.mask)
        self.center = np.array([float(xs.mean()), float(ys.mean())], np.float64)
        if min(xs.min(), ys.min(), self.width - 1 - xs.max(), self.height - 1 - ys.max()) < 5:
            raise ValueError('参考月盘触及画面边缘，请选择完整且留有余量的参考片')
        self.scale = self.disc_diameter / 1100
        self.ref_features = features(self.gray, self.mask, self.scale)
        self.lk_points = choose_lk_points(self.gray, self.mask, self.scale)
        self.lk_holdout = np.arange(len(self.lk_points)) % 3 == 0
        self.reference_stat = {'path': str(self.reference_path), 'size': self.reference_path.stat().st_size,
                               'mtime_ns': self.reference_path.stat().st_mtime_ns}
        self.config = {'application': 'MoonAlignGUI', 'algorithm_version': ALGORITHM_VERSION,
                       'reference': str(self.reference_path), 'reference_sha256': digest(ref_data),
                       'reference_stat': self.reference_stat, 'parameters': PARAMETERS,
                       'opencv_version': cv2.__version__, 'input_count': len(self.paths),
                       'shape': list(self.shape), 'disc_diameter_px': self.disc_diameter,
                       'scale_factor': self.scale,
                       'inventory_sha256': digest(json.dumps(self.inventory, sort_keys=True).encode())}
        self.fingerprint = digest(json.dumps(self.config, sort_keys=True).encode())

    def prepare_output(self):
        """Called only while holding the output-directory OS lock."""
        config_path = self.output / 'job_config.json'
        if config_path.is_file():
            if json.loads(config_path.read_text(encoding='utf-8')) != self.config:
                raise ValueError('输出目录已存在且不属于同一任务；请选择新的文件夹，或选择原任务目录续跑')
        else:
            if any(p.name != 'job.lock' for p in self.output.iterdir()):
                raise ValueError('输出目录非空且不属于本程序任务，请选择新的空文件夹')
            atomic_json(self.output / 'job_config.json', self.config)
            atomic_json(self.output / 'source_inventory.json', self.inventory)
        for directory in [self.frames, self.metrics, self.quarantine]:
            directory.mkdir(parents=True, exist_ok=True)
        expected = {p.name.casefold() for p in self.paths}
        extras = [p.name for p in self.frames.iterdir()
                  if p.suffix.lower() in ('.tif', '.tiff') and p.name.casefold() not in expected]
        if extras:
            raise ValueError('frames 目录含有不在本次输入清单中的 TIFF，请选择正确的任务目录：' + ', '.join(extras[:5]))
        needed = sum(self.width * self.height * 6 + 8192 for p in self.paths
                     if not (self.frames / p.name).is_file())
        if shutil.disk_usage(self.output).free < needed + max(2 * 1024**3, int(needed * .05)):
            raise ValueError('输出磁盘空间不足；需要容纳未压缩 16 位彩色 TIFF 及临时写入空间')
        atomic_json(self.reports / 'runtime.json', {'python': sys.version, 'opencv': cv2.__version__,
                    'numpy': np.__version__, 'workers': self.workers,
                    'compute_threads': self.compute_threads, 'performance_resources': self.resources,
                    'memory_policy': self.memory_policy,
                    'algorithm_version': ALGORITHM_VERSION})

    def record_path(self, path):
        return self.metrics / (path.name + '.json')

    def valid_resume(self, path):
        report = self.record_path(path)
        target = self.frames / path.name
        if not report.is_file() or not target.is_file():
            return None
        try:
            record = json.loads(report.read_text(encoding='utf-8'))
            if record['status'] != 'success' or record['job_fingerprint'] != self.fingerprint:
                return None
            stat = path.stat()
            if (record['source_stat'] != self.inventory_by_name[path.name] or
                    stat.st_size != record['source_stat']['size'] or
                    stat.st_mtime_ns != record['source_stat']['mtime_ns']):
                return None
            if digest(path.read_bytes()) != record['source_sha256']:
                return None
            data = target.read_bytes()
            if len(data) != record['output']['size_bytes'] or digest(data) != record['output']['sha256']:
                return None
            md = metadata(data)
            if (md['size'] != [self.width, self.height] or md['bits'] != [16, 16, 16] or
                    md['channels'] != 3 or md['photometric'] != 2 or md['orientation'] != 1 or md['compression'] != 1):
                return None
            record['resumed'] = True
            return record
        except Exception:
            return None

    def sift_pose(self, gray, mask):
        kp, desc = features(gray, mask, self.scale)
        rk, rd = self.ref_features
        pairs = cv2.BFMatcher().knnMatch(desc, rd, k=2)
        good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < .72 * p[1].distance]
        if len(good) < 100:
            raise ValueError('可确认的月面特征匹配不足')
        src = np.float32([kp[m.queryIdx].pt for m in good])
        dst = np.float32([rk[m.trainIdx].pt for m in good])
        hold = np.array([m.trainIdx % 4 == 0 for m in good])
        if hold.sum() < 40 or (~hold).sum() < 100:
            raise ValueError('独立特征验证点不足')
        initial, keep = cv2.estimateAffinePartial2D(src[~hold], dst[~hold], method=cv2.RANSAC,
                ransacReprojThreshold=1.5 * self.scale, maxIters=5000, confidence=.999, refineIters=20)
        if initial is None:
            raise ValueError('无法求得可靠的初始旋转角度')
        ids = np.flatnonzero(~hold)[keep.ravel().astype(bool)]
        matrix = rigid(src[ids], dst[ids])
        fit_error = np.linalg.norm(transform(src[ids], matrix) - dst[ids], axis=1)
        val_error = np.linalg.norm(transform(src[hold], matrix) - dst[hold], axis=1)
        coverage = point_coverage(dst[ids], self.center)
        record = {'matches': len(good), 'fit_inliers': len(ids), 'fit_median_px': float(np.median(fit_error)),
                  'holdout_points': int(hold.sum()), 'holdout_median_px': float(np.median(val_error)),
                  'holdout_consistency': float((val_error <= 2.5 * self.scale).mean()),
                  'diagnostic_scale': float(np.hypot(initial[0, 0], initial[1, 0])), **coverage}
        if (len(ids) < 150 or record['fit_median_px'] > self.scale or
                record['holdout_median_px'] > 1.25 * self.scale or record['holdout_consistency'] < .7 or
                min(coverage['extent_px']) < 500 * self.scale or coverage['quadrants'] < 3 or
                abs(record['diagnostic_scale'] - 1) > .01):
            raise ValueError('独立特征验证未通过：' + json.dumps(record, ensure_ascii=False))
        return matrix, record

    def fine_pose(self, gray, matrix):
        coarse = cv2.warpAffine(gray, matrix, (self.width, self.height), flags=cv2.INTER_CUBIC)
        q, valid = track(self.gray, coarse, self.lk_points, self.scale)
        hold, train = valid & self.lk_holdout, valid & ~self.lk_holdout
        before = summarize_tracking(self.lk_points, q, hold, self.center)
        chosen, applied, correction_angle, after = matrix, False, 0., None
        p = self.lk_points.reshape(-1, 2)
        if train.sum() >= 40:
            _, keep = cv2.estimateAffinePartial2D(q[train], p[train], method=cv2.RANSAC,
                    ransacReprojThreshold=.8 * self.scale, maxIters=3000, confidence=.999)
            if keep is not None:
                ids = np.flatnonzero(train)[keep.ravel().astype(bool)]
                if len(ids) >= 30:
                    correction = rigid(q[ids], p[ids])
                    correction_angle = angle(correction)
                    candidate = compose(correction, matrix)
                    candidate_gray = cv2.warpAffine(gray, candidate, (self.width, self.height), flags=cv2.INTER_CUBIC)
                    q2, valid2 = track(self.gray, candidate_gray, self.lk_points, self.scale)
                    common = hold & valid2
                    if common.sum() >= 25:
                        before = summarize_tracking(self.lk_points, q, common, self.center)
                        after = summarize_tracking(self.lk_points, q2, common, self.center)
                        if (after['median_px'] <= before['median_px'] * 1.01 + .002 * self.scale and
                                after['p90_px'] <= before['p90_px'] * 1.01 + .002 * self.scale and
                                abs(after['remaining_angle_deg']) <= abs(before['remaining_angle_deg']) + .002 and
                                after['remaining_center_shift_px'] <= before['remaining_center_shift_px'] + .01 * self.scale and
                                abs(correction_angle) <= .15):
                            chosen, applied = candidate, True
        return chosen, {'applied': applied, 'correction_angle_deg': correction_angle,
                        'coarse_holdout': before, 'candidate_holdout': after}

    def process(self, path):
        started = time.perf_counter()
        old = self.valid_resume(path)
        if old is not None:
            return old
        record = {'file': path.name, 'status': 'failed', 'job_fingerprint': self.fingerprint,
                  'source_stat': self.inventory_by_name[path.name], 'resumed': False}
        temporary = self.frames / (path.name + '.part')
        try:
            stat = path.stat()
            if stat.st_size != record['source_stat']['size'] or stat.st_mtime_ns != record['source_stat']['mtime_ns']:
                raise ValueError('原片在建立任务清单后发生变化')
            data = path.read_bytes()
            md = metadata(data)
            _check_metadata(md)
            if md['size'] != [self.width, self.height]:
                raise ValueError('图片尺寸与参考片不一致')
            rgb = read_rgb_bytes(data)
            record['source_sha256'] = digest(data)
            del data
            if path == self.reference_path:
                matrix = np.array([[1., 0, 0], [0, 1., 0]])
                aligned = rgb
                record['reference_passthrough'] = True
                record['validation'] = {'points': int(self.lk_holdout.sum()), 'median_px': 0., 'p90_px': 0.,
                    'remaining_angle_deg': 0., 'remaining_center_shift_px': 0.,
                    'extent_px': [self.disc_diameter, self.disc_diameter], 'quadrants': 4}
            else:
                gray = gray8(rgb)
                mask = lunar_mask(gray)
                ys, xs = np.nonzero(mask)
                if min(xs.min(), ys.min(), self.width - 1 - xs.max(), self.height - 1 - ys.max()) < 3:
                    raise ValueError('输入月盘切边')
                matrix, record['sift'] = self.sift_pose(gray, mask)
                matrix, record['refinement'] = self.fine_pose(gray, matrix)
                aligned = cv2.warpAffine(rgb, matrix, (self.width, self.height), flags=cv2.INTER_CUBIC,
                                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
                q, valid = track(self.gray, gray8(aligned), self.lk_points, self.scale)
                validation = summarize_tracking(self.lk_points, q, valid & self.lk_holdout, self.center)
                record['validation'] = validation
                if (validation['median_px'] > .9 * self.scale or validation['p90_px'] > 1.6 * self.scale or
                        abs(validation['remaining_angle_deg']) > .06 or
                        validation['remaining_center_shift_px'] > .6 * self.scale or
                        validation['quadrants'] < 3 or min(validation['extent_px']) < 500 * self.scale):
                    raise ValueError('最终独立纹理校验未通过：' + json.dumps(validation, ensure_ascii=False))
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                boundary = np.concatenate(contours, axis=0).reshape(-1, 2).astype(np.float32)
                moved = transform(boundary, matrix)
                bounds = [float(moved[:, 0].min()), float(moved[:, 1].min()),
                          float(moved[:, 0].max()), float(moved[:, 1].max())]
                record['disc_bounds_px'] = bounds
                if bounds[0] < 3 or bounds[1] < 3 or bounds[2] > self.width - 4 or bounds[3] > self.height - 4:
                    raise ValueError('对齐后的月盘会被裁切')
            record['angle_deg'] = angle(matrix)
            record['matrix'] = matrix.tolist()
            record['center_shift_px'] = float(np.linalg.norm(transform(self.center, matrix) - self.center))
            if record['center_shift_px'] > 150 * self.scale:
                raise ValueError('月盘中心位移过大，无法可靠配准')
            write_tiff(temporary, aligned, md['icc'])
            record['output'] = verify_written(temporary, aligned, md['icc'])
            latest = path.stat()
            if latest.st_size != stat.st_size or latest.st_mtime_ns != stat.st_mtime_ns:
                raise ValueError('处理期间原片发生变化')
            os.replace(temporary, self.frames / path.name)
            record['status'] = 'success'
        except Exception as error:
            record['error'] = str(error)
            record['traceback'] = traceback.format_exc(limit=3)
            if temporary.exists() and temporary.parent.resolve() == self.frames.resolve():
                temporary.unlink()
            target = self.frames / path.name
            if target.is_file() and target.parent.resolve() == self.frames.resolve():
                destination = self.quarantine / (path.name + '.' + str(time.time_ns()))
                os.replace(target, destination)
                record['quarantined_previous_output'] = str(destination)
        record['seconds'] = time.perf_counter() - started
        atomic_json(self.record_path(path), record)
        return record

    def run_stage(self, paths, stage):
        self.stage = stage
        self.processing_started = time.perf_counter()
        self.emit('message', message='跨时段小批验证' if stage == 'pilot' else '批量精细旋转配准')
        iterator, pending = iter(paths), {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            def fill():
                while not self.cancel.is_set() and len(pending) < self.workers * 2:
                    path = next(iterator, None)
                    if path is None:
                        break
                    pending[pool.submit(self.process, path)] = path
            fill()
            while pending:
                if self.cancel.is_set():
                    for future in list(pending):
                        if future.cancel():
                            pending.pop(future)
                if not pending:
                    break
                completed, _ = wait(pending, timeout=.2, return_when=FIRST_COMPLETED)
                for future in completed:
                    pending.pop(future)
                    result = future.result()
                    self.records[result['file']] = result
                    self.emit('frame', filename=result['file'], status=result['status'],
                              resumed=result.get('resumed', False),
                              message=result.get('error', '已核验并恢复' if result.get('resumed') else '配准和 TIFF 写入校验通过'))
                fill()
        self.processing_seconds += time.perf_counter() - self.processing_started
        self.processing_started = None

    def summary(self, status, **extra):
        good = [r for r in self.records.values() if r['status'] == 'success']
        bad = [r for r in self.records.values() if r['status'] != 'success']
        return {'status': status, 'total': len(self.paths), 'processed': len(self.records),
                'success': len(good), 'failed': len(bad), 'cancelled': status == 'cancelled',
                'passed': status == 'completed' and not bad and len(good) == len(self.paths),
                'pilot_passed': self.pilot_passed,
                'output_directory': str(self.frames), 'report_directory': str(self.reports),
                'failed_files': [r['file'] for r in bad],
                'resumed_frames': sum(r.get('resumed', False) for r in good),
                'refined_frames': sum(r.get('refinement', {}).get('applied', False) for r in good),
                'elapsed_seconds': time.perf_counter() - self.started,
                **self.progress_counters(),
                'median_independent_texture_error_px': float(np.median([r['validation']['median_px'] for r in good])) if good else None,
                'worst_independent_remaining_angle_deg': max((abs(r['validation']['remaining_angle_deg']) for r in good), default=None),
                **extra}

    def write_reports(self, summary):
        atomic_json(self.reports / 'summary.json', summary)
        fields = ['file', 'status', 'angle_deg', 'center_shift_px', 'holdout_median_px',
                  'independent_median_px', 'independent_p90_px', 'remaining_angle_deg',
                  'refined', 'resumed', 'seconds', 'error']
        temp = self.reports / 'alignment.csv.tmp'
        with temp.open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for r in sorted(self.records.values(), key=lambda r: r['file'].casefold()):
                validation = r.get('validation', {})
                writer.writerow({'file': r['file'], 'status': r['status'], 'angle_deg': r.get('angle_deg'),
                    'center_shift_px': r.get('center_shift_px'), 'holdout_median_px': r.get('sift', {}).get('holdout_median_px'),
                    'independent_median_px': validation.get('median_px'), 'independent_p90_px': validation.get('p90_px'),
                    'remaining_angle_deg': validation.get('remaining_angle_deg'),
                    'refined': r.get('refinement', {}).get('applied', False), 'resumed': r.get('resumed', False),
                    'seconds': r.get('seconds'), 'error': r.get('error', '')})
        os.replace(temp, self.reports / 'alignment.csv')

    def audit(self):
        self.stage = 'audit'
        self.audit_done = 0
        self.emit('message', message='核对全部输出校验和、格式、文件名及原片状态')
        problems, changed = [], []
        for index, path in enumerate(self.paths, 1):
            if self.cancel.is_set():
                return {'cancelled_during_audit': True, 'audit_passed': False}
            stat = path.stat()
            expected = self.inventory_by_name[path.name]
            if stat.st_size != expected['size'] or stat.st_mtime_ns != expected['mtime_ns']:
                changed.append(path.name)
            record = self.records.get(path.name)
            if record and record['status'] == 'success' and self.valid_resume(path) is None:
                problems.append(path.name)
            self.audit_done = index
            if index % 50 == 0 or index == len(self.paths):
                self.emit('message', message=f'输出校验 {index}/{len(self.paths)}')
        ref_stat = self.reference_path.stat()
        if (ref_stat.st_size != self.reference_stat['size'] or
                ref_stat.st_mtime_ns != self.reference_stat['mtime_ns']):
            changed.append(str(self.reference_path))
        expected_names = {r['file'] for r in self.records.values() if r['status'] == 'success'}
        actual_names = {p.name for p in self.frames.iterdir() if p.suffix.lower() in ('.tif', '.tiff')}
        return {'audit_passed': not problems and not changed and actual_names == expected_names,
                'audit_problem_files': problems, 'source_files_changed_by_size_or_mtime': changed,
                'unexpected_output_files': sorted(actual_names - expected_names),
                'missing_output_files': sorted(expected_names - actual_names),
                'actual_tiff_count': len(actual_names)}

    def run(self):
        if self.cancel.is_set():
            summary = self.summary('cancelled', message='任务已取消')
            self.emit('done', summary=summary, status='cancelled', message=summary['message'])
            return summary
        self.initialize()
        if self.output.exists():
            if not self.output.is_dir():
                raise ValueError('输出路径不是文件夹')
            if not (self.output / 'job_config.json').is_file() and any(
                    p.name != 'job.lock' for p in self.output.iterdir()):
                raise ValueError('输出目录非空且不属于本程序任务，请选择新的空文件夹')
        else:
            self.output.mkdir()
        with _JobLock(self.output / 'job.lock'):
            self.prepare_output()
            pilot_count = min(64, len(self.paths))
            ids = set(np.linspace(0, len(self.paths) - 1, pilot_count).round().astype(int).tolist())
            pilot_paths = [p for i, p in enumerate(self.paths) if i in ids or p == self.reference_path]
            self.run_stage(pilot_paths, 'pilot')
            if self.cancel.is_set():
                summary = self.summary('cancelled', message='已安全停止，可使用相同选择和输出目录继续')
            elif any(r['status'] != 'success' for r in self.records.values()):
                summary = self.summary('pilot_failed', message='小批验证未全部通过，已停止全量处理，请查看失败清单')
                atomic_json(self.reports / 'pilot_summary.json', summary)
            else:
                self.pilot_passed = True
                atomic_json(self.reports / 'pilot_summary.json', self.summary('pilot_passed', passed=True))
                self.run_stage([p for p in self.paths if p.name not in self.records], 'all')
                if self.cancel.is_set():
                    summary = self.summary('cancelled', message='已安全停止，可使用相同选择和输出目录继续')
                else:
                    audit = self.audit()
                    if audit.get('cancelled_during_audit'):
                        summary = self.summary('cancelled', **audit, message='校验已暂停，可续跑完成校验')
                    else:
                        summary = self.summary('completed', **audit,
                            message=f"处理完成：成功 {sum(r['status'] == 'success' for r in self.records.values())}，失败 {sum(r['status'] != 'success' for r in self.records.values())}")
                        summary['passed'] = summary['passed'] and audit['audit_passed']
            self.write_reports(summary)
        self.emit('done', **{k:v for k,v in summary.items() if k not in ('event', 'done')}, summary=summary)
        return summary


def run_alignment(files, reference, output, workers=3, progress=None, cancel_event=None, compute_threads=1,
                  memory_policy='conservative'):
    """Pilot -> full selected sequence -> integrity audit; no input file is written.

    Progress callbacks run from the orchestration thread, not the GUI thread.
    Cancellation stops new submissions and safely waits for current image writes.
    Repeat with identical inputs/reference/output to resume verified checkpoints.
    Expanded memory policy changes only the RAM reserve, never pixel processing
    or quality gates. Resource changes do not invalidate verified checkpoints.
    """
    if not _COMPUTE_LOCK.acquire(blocking=False):
        raise RuntimeError('同一程序内已有配准任务运行；请等待完成或安全停止后再开始')
    previous_threads = None
    try:
        previous_threads = cv2.getNumThreads()
        job = _Job(files, reference, output, workers, progress, cancel_event, compute_threads, memory_policy)
        cv2.setNumThreads(job.compute_threads)
        return job.run()
    finally:
        try:
            if previous_threads is not None:
                cv2.setNumThreads(previous_threads)
        finally:
            _COMPUTE_LOCK.release()

