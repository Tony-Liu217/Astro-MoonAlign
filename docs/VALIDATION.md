# Validation / 验证范围

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
