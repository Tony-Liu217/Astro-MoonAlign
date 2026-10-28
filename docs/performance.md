# Performance controls / 性能设置

MoonAlign v1.1.1 — preview release.  
MoonAlign v1.1.1：预览版。

## 中文

### 四种模式调整什么

| 模式 | 用途 |
| --- | --- |
| 安静（`quiet`） | 较少并行工作，给其他程序保留更多资源 |
| 均衡（`balanced`） | 默认；根据图幅与本机资源选择并发 |
| 高性能（`performance`） | 允许更多并行工作，适合电脑空闲且内存充足时 |
| 自定义（`custom`） | 自行选择同时处理图片数与 OpenCV 内部线程数 |

两项设置含义不同：“同时处理图片数”表示并行配准几张照片；“OpenCV 内部线程数”影响每张照片内部的图像计算。把两者同时调大可能争用 CPU、内存或磁盘。程序会限制资源配置；估算不等于对系统负载或剩余内存的保证。

界面在“资源模式”中提供“安静 / 均衡（推荐） / 高性能 / 自定义”。选择自定义后可调整“并发照片”和“每项计算线程”；其余模式显示自动配置。开始前查看“实际”资源摘要，以程序最终选用的并发和线程数为准。

运行中的速度与“配准预计剩余”只描述配准阶段，续跑会另报已复用数量。TIFF 完整性与哈希检查有独立进度；配准剩余时间不包含这段最终检查，初始估计也会随处理样本变化。

所有模式使用相同的刚性配准模型和检查标准。没有通过减少校验、使用低精度彩色输出或缩小最终图片提速。源文件仍只读，最终 RGB16 图像仍只做一次几何重采样。资源设置不纳入配准配置，因此相同任务可在调整并发后继续运行；更换输入、参考片或算法版本仍需新任务目录。

### v1.1.1：放宽内存限制（高级）

自定义模式新增“放宽内存限制（高级）”，默认关闭；安静、均衡、高性能模式仍使用保守策略。

- 默认策略预留 `max(3 GiB, 当前可用内存 × 25%)`；放宽后预留 `max(1 GiB, 当前可用内存 × 10%)`。
- 只改变预留预算，每张照片的内存估算、全局开销、CPU 线程上限和完整配准/文件检查均不变。这会允许资源足够时选用更高并发，但增加换页、卡顿或内存不足的可能性。
- 先在当前作业中安全取消，等待在途图片完成；然后用新版、原输入选择、同一参考片和同一输出目录续跑。合格结果会校验后复用，不需要从头配准。
- 电脑空闲并释放内存后，从自定义 **4 × 2** 试起；只有界面实际允许时，再考虑 **6 × 2**。当前 20 逻辑核的 CPU 预算最多允许 **5 × 4**，不能盲设 **6 × 4**。查看“实际”资源摘要，限制仍不足时先减少其他程序的内存占用。

增加并发不等于必然加速；内存已高度占用时，更多工作可能因换页而更慢。本补丁没有新增 32 张速度基准，下面的数据保持为 v1.1.0 的历史对照。

### v1.1.0 实测方法与范围

测试电脑为 Intel Core i7-12700KF（12 物理核 / 20 逻辑核）、32 GiB 内存。从一组近满月序列均匀抽取 32 张 1800 × 1800 RGB16 TIFF，使用同一参考片和新的输出目录。各组在独立的正常优先级 Windows 进程中运行，原有 MoonAlign 当时空闲。以下总耗时包含初始化、配准、原片 SHA256、TIFF 原子写入与精确读回、最终完整哈希审计。

| 实际并发 × 每项线程 | 总耗时 | 全流程平均速度 | 进程私有内存峰值 |
| --- | ---: | ---: | ---: |
| 旧配置 3 × 1 | 15.937 秒 | 2.008 张/秒 | 2.95 GiB |
| 新配置 3 × 2 | 13.581 秒 | 2.356 张/秒 | 2.92 GiB |
| 新配置 3 × 4 | 12.246 秒 | 2.613 张/秒 | 2.91 GiB |

这组测试中，3 × 2 比旧配置总耗时少约 14.8%；3 × 4 总耗时少约 **23.16%**、全流程吞吐提高约 **30.15%**。三组均 32/32 通过，**32 张输出的 SHA256 逐一完全相同**；独立纹理残差中位均约 0.327749 像素、最大剩余旋转均约 0.019397°，13 张采用细化。相同输出是这组实测结果，不代表所有电脑、图片或线程设置都保证逐像素相同。

测试时当前可用内存约 7 GiB，自动配置因此将并发限制为 3 张；安静、均衡、高性能分别选择了 3 × 1、3 × 2、3 × 4。内存充足时，并发可能更高；高性能模式只有在内存限制并发、不会减少同时处理照片数且 CPU 线程预算允许时，才自适应采用 4 个计算线程。模式名称不对应固定的“6 张”或“10 张”，以启动前的实际资源摘要为准。

这是单组同机对照，并非多轮统计或对任意素材的速度保证。内存数字为进程私有内存，与操作系统文件缓存及界面的保护性资源估算不同。表中平均速度包含最终审计，界面显示的配准阶段速度不包含最终审计，两者口径不同。

不含拍摄文件及本机路径的结构化结果见 [performance-results-v1.1.0.json](performance-results-v1.1.0.json)。

性能随图幅、月面纹理、CPU、可用内存、存储及其他程序负载变化。更高并发未必持续更快。首次使用请先小批验证；发生内存紧张或影响其他程序时，降低并发或选择安静模式。

v1.0 的实拍与封装验证见 [VALIDATION.md](VALIDATION.md)。本次性能更新不表示 GUI 版本已经重新完整处理 4080 张，也不代替实际界面点击或跨电脑兼容性验收。

## English

### What the modes control

| Mode | Purpose |
| --- | --- |
| Quiet (`quiet`) | Less parallel work, leaving more resources for other applications |
| Balanced (`balanced`) | Default; chooses concurrency using the canvas size and host resources |
| Performance (`performance`) | Allows more parallel work when the machine is otherwise idle and has sufficient memory |
| Custom (`custom`) | Choose image-level concurrency and OpenCV's internal thread count |

The settings have different meanings: image concurrency controls how many frames are aligned at once; OpenCV threads affect computations within a frame. Increasing both can create contention for CPU, memory or storage. Resource limits are applied, but estimates are not guarantees of system load or available memory.

The Chinese GUI exposes these under “资源模式”. Custom mode enables “并发照片” (concurrent images) and “每项计算线程” (compute threads per item); the other modes display automatically chosen values. Check the “实际” resource summary for the configuration that will actually be used.

Live speed and alignment ETA describe the alignment stage; resumed outputs are counted separately. TIFF integrity and hash verification have their own final progress. The alignment ETA excludes that final check and will change as more frames are measured.

All modes retain the same rigid model and quality checks. Speed does not come from skipping validation, reducing output colour precision or resizing the final images. Sources remain read only, and final RGB16 data is geometrically resampled once. Resource settings are excluded from the registration configuration, allowing the same job to resume with different concurrency. Changed inputs, reference or algorithm versions still require a new job directory.

### v1.1.1: advanced memory headroom

Custom mode adds “放宽内存限制（高级）” (relax memory limits, advanced), off by default. Quiet, Balanced and Performance retain the conservative policy.

- The default reserve is `max(3 GiB, available RAM × 25%)`; expanded mode uses `max(1 GiB, available RAM × 10%)`.
- Only reserved headroom changes. Per-frame memory estimates, global overhead, CPU thread limits and full registration/file checks remain unchanged. More concurrency can become available, with increased risk of paging, stutter or insufficient memory.
- Safely cancel the current job and wait for in-flight frames to finish. Resume using the new version with the same selected inputs, reference and output folder; verified outputs are reused rather than registered from scratch.
- On an otherwise idle machine after freeing memory, start with Custom **4 × 2**, considering **6 × 2** only when the actual resource limit permits it. A 20-logical-CPU budget permits at most **5 × 4**, not **6 × 4**. Consult the actual resource summary, and free memory from other programs if limits remain too low.

Higher concurrency does not guarantee higher speed; paging can make a heavily loaded machine slower. This patch adds no new 32-frame speed benchmark. The following remains the historical v1.1.0 comparison.

### v1.1.0 measurement method and scope

The test machine was an Intel Core i7-12700KF (12 physical / 20 logical cores), with 32 GiB RAM. The same reference and 32 uniformly sampled 1800 × 1800 RGB16 TIFFs from a near-full lunar sequence were used with fresh output directories. Each run used a separate Windows process at normal priority; the existing MoonAlign application was idle. Total times include initialization, alignment, source SHA256, atomic TIFF write and exact readback, and the final full hash audit.

| Actual concurrent frames × threads per item | Total time | End-to-end average | Peak private process memory |
| --- | ---: | ---: | ---: |
| Previous configuration 3 × 1 | 15.937 s | 2.008 frames/s | 2.95 GiB |
| New configuration 3 × 2 | 13.581 s | 2.356 frames/s | 2.92 GiB |
| New configuration 3 × 4 | 12.246 s | 2.613 frames/s | 2.91 GiB |

For this sample, 3 × 2 reduced total time by about 14.8%. The 3 × 4 configuration reduced it by **23.16%**, increasing end-to-end throughput by **30.15%**. All runs passed 32/32 frames, and **all 32 output SHA256 hashes matched exactly**. Each run had a median independent texture residual of approximately 0.327749 px, maximum remaining rotation of approximately 0.019397°, and 13 refined frames. Identical output is an observation for this sample, not a pixel-identity guarantee for every computer, input or thread setting.

About 7 GiB of RAM was available at the time, so automatic resource limits capped concurrency at three frames: Quiet, Balanced and Performance selected 3 × 1, 3 × 2 and 3 × 4. More available memory can permit higher concurrency. Performance mode adapts to four compute threads only when memory limits concurrency, image concurrency is not reduced, and the CPU thread budget permits it. Modes do not correspond to a fixed six or ten frames; consult the actual resource summary before starting.

This is one same-machine comparison, not a repeated statistical benchmark or a speed guarantee for arbitrary inputs. Private process memory differs from operating-system file caches and the GUI's conservative resource estimate. The table's average includes the final audit; the live alignment-stage speed excludes that audit.

The structured measurements, without photographs or local paths, are in [performance-results-v1.1.0.json](performance-results-v1.1.0.json).

Performance depends on dimensions, lunar texture, CPU, available memory, storage and other applications. Higher concurrency is not always faster. Start with a small batch; reduce concurrency or use Quiet mode if memory is tight or other applications are affected.

See [VALIDATION.md](VALIDATION.md) for the v1.0 real-image and packaging validation. This update does not mean the GUI edition has rerun the full 4080-frame sequence, nor does it replace native UI click-through or cross-computer acceptance testing.
