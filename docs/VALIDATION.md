# Validation / 验证范围

## v1.1.1 — 2026-10-28

**52 windowless regression checks passed: 20 core checks and 32 GUI logic checks.** The optional real-data integration test remains opt-in.

**52 项无窗口回归检查通过：核心 20 项、GUI 逻辑 32 项。** 真实素材集成测试仍按需启用。

The v1.1.1 frozen executable passed a windowless self-check with Python environment variables removed, including the expanded memory profile, bundled imports, SIFT, exact RGB16 TIFF round trip and rigid-transform numerics. No native UI operation or new 32-frame benchmark was performed for this patch.

v1.1.1 冻结 EXE 已在清理 Python 环境变量后通过无窗口自检，覆盖放宽内存策略、内置依赖、SIFT、RGB16 TIFF 精确往返和刚性变换数值。本补丁没有进行原生 UI 操作或新增 32 张基准。

Core resource-policy checks cover the unchanged conservative default, expanded headroom, RAM and CPU limits, and resuming the same job across a policy change without changing outputs. Registration mathematics, quality gates and checkpoint identity are unchanged. This patch does not add a new 32-frame speed benchmark; the v1.1.0 comparison below remains historical. The advanced checkbox has not been validated through native UI interaction.

本补丁的资源策略检查覆盖原保守默认值、放宽预留预算、RAM/CPU 上限，以及切换策略后继续相同任务、不改写合格输出。配准数学、质量门槛及检查点身份不变。未新增 32 张测速，以下 v1.1.0 数据作为历史对照；新增高级复选框尚未经过原生界面操作验证。

## v1.1.0 — 2026-10-28

- **42 windowless regression checks passed:** 16 core checks and 26 GUI logic checks, including an integrated rerun. The GUI engine also passed a 10-frame real-data cancellation/resume/damaged-output check, and resumed 32 previously verified v1 outputs across changed resource settings.
- A normal-priority, same-machine 32-frame comparison passed at 3 × 1, 3 × 2 and 3 × 4 resources. All 32 TIFF SHA256 hashes matched exactly across runs; see [performance measurements](performance.md) for times, memory and scope.
- Registration mathematics, quality gates and the algorithm/checkpoint identity remain unchanged. The v1.1.0 frozen executable passed a windowless check with Python environment variables removed: imports, all three automatic resource profiles, SIFT, exact RGB16 TIFF round trip and rigid-transform numerics.
- **Native GUI validation was partial:** the v1.1 window opened, with resource controls, memory summary, speed/ETA and Start visible; the folder dialog opened normally. Input selection through completed processing has not been exercised through the GUI. Cross-computer and newly provisioned build-environment testing remain pending.

- **42 项无窗口回归检查通过：**核心 16 项、GUI 逻辑 26 项，并完成一次综合复跑。另有 10 张真实素材的取消/续跑/损坏重建检查通过；32 张 v1 合格输出在改变资源设置后续跑通过。
- 正常优先级、同机 32 张对照在 3 × 1、3 × 2、3 × 4 配置下均通过，32 张 TIFF 的 SHA256 跨组逐一相同；耗时、内存及适用范围见[性能实测](performance.md)。
- 配准数学、质量门槛与算法/检查点身份保持不变。v1.1.0 冻结 EXE 已清理 Python 环境变量后通过无窗口检查：依赖导入、三个自动资源模式、SIFT、RGB16 TIFF 精确往返及刚性变换数值。
- **原生 GUI 验证为部分完成：**v1.1 窗口可打开，资源模式控件、内存摘要、速度/ETA 和开始按钮可见，文件夹对话框正常弹出；尚未通过 GUI 运行完整选图到处理完成的流程。跨电脑及全新构建环境测试仍待完成。

## v1.0.0 baseline / 基础验证

Validation recorded on 2026-10-27 for MoonAlign 1.0.0, Windows x64.

## English

- **19 automated checks passed:** 10 registration/file-safety checks and 9 GUI completion-state logic checks. These do not create a GUI window. Coverage includes rigid transforms without scale/shear, RGB16 TIFF round trips, ICC preservation, format rejection, output isolation, locking, and truthful completion/error states.
- **10 real lunar TIFFs passed:** images sampled across one observing sequence were registered, then independently checked. Median texture residual was approximately 0.337 px; the largest remaining rotation in this sample was approximately 0.0119°. These measurements describe this sample, not a general accuracy guarantee.
- Cancellation, resumption, reuse of verified outputs, selective processing, and rebuilding one deliberately damaged output were exercised. A separate 2400 × 2400 known-transform test passed for three images. Test inputs remained unchanged.
- The **Windows portable executable passed a windowless runtime self-check** with Python environment variables removed: bundled imports, SIFT availability, exact RGB16 TIFF round trip, and rigid-transform numerics. Archive CRC and application-source fingerprints were also checked.
- **Earlier command-line implementation:** the underlying method had previously processed and audited 4,080 images. The GUI edition has **not** repeated that entire 4,080-image run.

The real-image evidence is primarily PIPP-converted, 1800 × 1800 RGB16 TIFFs containing a complete near-full Moon about 1100 px across. Other cameras, lunar phases, dimensions, and observing conditions require their own small-batch check. Actual GUI click-through, cross-computer compatibility, and a build in a newly provisioned environment remain to be independently verified.

No test photographs or private observing data are included in the repository or release archives. The optional real-data integration test requires locally supplied paths through environment variables.

## 中文

- **19 项自动检查通过：**10 项核心配准与文件安全检查、9 项界面完成状态逻辑检查，均不创建 GUI 窗口。覆盖无缩放/剪切的刚性变换、RGB16 TIFF 精确往返、ICC 保留、输入格式拒绝、输出隔离、独占锁和真实完成/错误状态。
- **10 张真实月面 TIFF 通过：**从同一拍摄序列跨时段抽样并配准，另做独立检验。该样本纹理残差中位约 0.337 像素，最大剩余旋转约 0.0119°；这些数字不代表普遍精度保证。
- 已验证取消、续跑、复用合格结果、部分图片选择，以及故意损坏一张输出后单独重建。另有 3 张 2400 × 2400 的已知变换测试通过。测试输入保持不变。
- **Windows 便携 EXE 的无窗口运行检查通过：**清理 Python 环境变量后，验证内置依赖、SIFT、RGB16 TIFF 精确往返和刚性变换数值；另核验压缩包 CRC 及应用源码指纹。
- **先前命令行版本**已用同一方法处理并审计 4080 张图片；GUI 版本尚未重新完整运行这 4080 张。

实拍验证主要针对 PIPP 后 1800 × 1800 的 RGB16 TIFF、月盘约 1100 像素的完整近满月。其他器材、月相、尺寸及拍摄条件应先小批验证。实际 GUI 点击流程、跨电脑兼容性和全新环境构建仍待独立验证。

仓库及发布包不包含测试照片或私人拍摄资料。可选的真实素材集成测试通过环境变量指定使用者自己的本地文件路径。
