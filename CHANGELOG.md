# Changelog / 更新记录

## v1.1.1 — Advanced memory policy / 高级内存策略 — 2026-10-28

Preview release / 预览版。

- Add an opt-in Custom-mode “放宽内存限制（高级）” checkbox. The conservative default reserves at least 3 GiB or 25% of available memory, whichever is larger; expanded mode reserves at least 1 GiB or 10%. Per-frame estimates, CPU limits, registration quality and checkpoint compatibility remain unchanged.
- More concurrency is conditional on current resources, not a guaranteed speed increase. No new 32-frame performance benchmark was run for this patch; v1.1.0 measurements remain historical evidence.
- 自定义模式新增默认关闭的“放宽内存限制（高级）”。默认策略保留至少 3 GiB 或当前可用内存 25% 中较大者，放宽后保留至少 1 GiB 或 10%；每张内存估算、CPU 上限、配准质量与检查点兼容性不变。
- 能否增加并发取决于当前资源，不保证提速。本补丁未新增 32 张性能基准，v1.1.0 的测量作为历史记录保留。

## v1.1.0 — Performance controls / 性能选项 — 2026-10-28

Included in v1.1.1; no separate public release. / 功能并入 v1.1.1，不单独发布此中间版本。

### English

- Add Quiet, Balanced, Performance and Custom resource modes, with Balanced as the default.
- Allow image-level concurrency and OpenCV thread count to be selected independently, within the engine's resource limits.
- Keep the registration mathematics, quality gates, RGB16 output and final integrity audit unchanged; resource changes preserve compatibility with the same job's checkpoints.
- Keep versioned build output under `release/v1.1.0/`, generate SHA256 checksums, and check build dependencies against the pinned requirements.
- Document performance measurements separately from the historical v1.0 validation; see [performance notes](docs/performance.md).
- In a normal-priority 32-frame comparison, 3 concurrent frames with 4 compute threads reduced total time from 15.937 s to 12.246 s (23.16% less); all output hashes matched the previous 3 × 1 configuration. This describes the tested sample, not a universal speed guarantee.

### 中文

- 增加安静、均衡、高性能和自定义四种资源模式，默认均衡。
- 可在引擎资源限制内，分别设置同时处理图片数与 OpenCV 内部线程数。
- 配准数学、质量门槛、RGB16 输出及最终完整性审计保持不变；只调整资源设置可继续相同任务的检查点。
- 构建产物单独保存到 `release/v1.1.0/`，生成 SHA256 校验文件，并核对固定依赖版本。
- 性能实测与 v1.0 历史验证分开说明，见[性能说明](docs/performance.md)。
- 正常优先级的 32 张对照中，3 张并发 × 4 计算线程将全流程耗时从 15.937 秒降至 12.246 秒（少 23.16%），输出哈希与旧 3 × 1 配置全部相同；不代表任意素材都具有相同加速幅度。

## v1.0.0 — Initial preview / 初版预览 — 2026-10-28

### English

- Portable Windows x64 GUI for rigid rotation and translation registration of full lunar discs between PIPP and AutoStakkert!.
- Select all or part of a TIFF sequence, choose a reference image and an independent output folder.
- Automatic pilot verification, batch processing, independent alignment checks and final output integrity audit.
- Preserve RGB with 16 bits per channel, original filenames and existing ICC profiles; source files are read-only.
- Background progress reporting, safe cancellation, verified resume and per-frame JSON/CSV reports.
- Include source code, build instructions, MIT license and third-party notices.

The GUI is in Chinese. This is an early release: complete GUI click-through and cross-machine compatibility testing are still pending. See [validation scope](docs/VALIDATION.md).

### 中文

- Windows x64 便携图形程序，在 PIPP 后、AutoStakkert! 前对完整月盘做整体旋转和平移配准。
- 支持文件夹内全部或部分 TIFF、参考片选择，以及独立的输出目录。
- 自动小批验证、批量处理、独立配准检查与最终输出完整性校验。
- 保留 RGB 每通道 16 位、原文件名及已有 ICC；原片只读。
- 后台进度、安全取消、校验后续跑，以及逐张 JSON / CSV 报告。
- 提供源码、构建说明、MIT 许可和第三方许可说明。

界面为中文。本版是早期发布，完整界面点击流程及跨电脑兼容性测试仍待完成，详见[验证范围](docs/VALIDATION.md)。
