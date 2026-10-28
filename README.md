# Astro-MoonAlign

**为完整月盘序列做精细旋转与平移配准，再交给 AutoStakkert! 叠加。**  
**Fine rotation and translation alignment for full-disc lunar sequences, ready for stacking in AutoStakkert!**

[下载 v1.0.0 初版预览 · Windows x64 便携版 / Download preview portable ZIP](https://github.com/Tony-Liu217/Astro-MoonAlign/releases/download/v1.0.0/MoonAlign_Windows_x64_v1.0.0.zip) · [版本与校验文件 / Release files](https://github.com/Tony-Liu217/Astro-MoonAlign/releases/tag/v1.0.0) · [English](#english)

解压后运行 `MoonAlign.exe`，无需安装 Python。请保留整个便携文件夹。当前界面为中文。  
Extract and run `MoonAlign.exe`; Python is not required. Keep the entire portable folder together. **GUI currently in Chinese; English instructions below.** This is the v1.0.0 preview release.

## 中文

### 用来解决什么

普通三脚架拍摄一批月亮照片时，即使已经在 PIPP 中居中，月面仍可能随时间旋转。只固定一个锚点，叠加后就容易出现外围重影。

MoonAlign 将每张照片的整体方向和位置对齐到同一张参考片，输出独立的 **16 位彩色 TIFF 序列**。它使用月面纹理匹配、刚性变换和独立检查；不需要手动逐张旋转。随后仍由 AutoStakkert! 完成质量排序、局部对齐和叠加。

```text
RAW / NEF → PIPP → MoonAlign → AutoStakkert! → waveSharp / 彩月后期
                    整体配准       选帧、局部对齐、叠加
```

PIPP、AutoStakkert! 和后期软件需另行准备。MoonAlign 在本机处理照片，不上传图片，也不需要账号。

### 快速开始

1. 从上方链接下载便携 ZIP，完整解压，双击 `MoonAlign.exe`。不要只复制 EXE，也不要删除 `_internal` 文件夹。
2. 在 PIPP 中将 RAW 解码为 **RGB 三通道、每通道 16 位的 TIFF**，统一居中和裁剪尺寸。每张保留完整月盘与足够黑边；采用一致的白平衡与色彩设置。关闭黑白转换、缩放、锐化、降噪和逐帧自动亮度均衡。
3. 在 MoonAlign 中选择 TIFF 文件夹，勾选全部或部分图片。支持 `.tif` 和 `.tiff`；不自动进入子文件夹。建议第一次先选十几张，覆盖整组的首、中、末段及旋转较大的时刻。
4. 从所选图片中指定一张清晰、完整的参考片，通常选择靠近拍摄时段中间的照片。默认参考片只方便开始操作，并不代表程序已经挑出最清晰的一张。
5. 选择独立的输出目录并开始。可以填写新目录、选择空目录，或选择本程序同一任务的已有输出目录。程序自动先做跨时段小批验证，通过后处理全部所选图片，并在结束时检查输出。
6. 看到检查通过后，抽查输出的月缘、月海和环形山，再将 **`frames/` 中的 TIFF** 导入 AutoStakkert!。先以常规倍率叠加检查，再决定是否尝试 Drizzle。

可以点击取消；程序会让在途图片安全完成后停止。使用**相同的图片选择、参考片和输出目录**重新开始，即可校验检查点并续跑；已经通过且未变化的输出会复用。更换素材、参考片或算法版本时，请使用新输出目录。

### 输入与适用边界

| 项目 | v1.0.0 要求 |
| --- | --- |
| 文件 | 同一文件夹内的 `.tif` / `.tiff`，RGB 三通道，每通道 16 位 |
| 图幅 | 所选图片尺寸一致，每边 800–6000 像素，方向正常 |
| 月盘 | 完整近满月，等效直径至少 800 像素，推荐 1000 像素以上 |
| 黑边 | 月盘不贴边，留出旋转和位移后的空间 |
| 拍摄条件 | 同一批素材，焦距、增距镜、缩放和采样尺度保持一致 |

本版主要验证了 PIPP 后 1800×1800、月盘约 1100 像素的近满月。输入不限定相机品牌；其他器材、图幅和月相应先小批试验。Windows 文件属性中的“位深度 48”表示 RGB 各通道 16 位；DPI 数值不影响配准。

程序只校正**整体旋转与平移**，固定尺度，不做局部形变。它不叠加、锐化、增强颜色或生成细节，也不能修复失焦、运动模糊、过曝、云遮、缺失月缘和视宁度造成的局部变形。不同焦距、缩放倍率或增距镜造成的尺度差异不在校正范围内。不要混合不同夜晚或明显不同月相的照片；局部月面、薄月牙、月食和低纹理图像尚未完成实拍验证。

通过自动检查不代表绝对无误，也不等于画质最佳。请继续在 AutoStakkert! 中做质量筛选和局部对齐。

### 输出与原片保护

```text
所选输出目录/
├─ frames/                检查通过的 TIFF，保留原文件名
├─ reports/               汇总、CSV 和逐张检查结果
├─ job_config.json        任务配置，用于续跑
├─ source_inventory.json  输入清单，用于检查输入变化
└─ quarantine/            必要时隔离失效的旧输出
```

- 原始文件只读，不改写。输入目录与输出目录不能重叠。
- 输出为无压缩 RGB TIFF，每通道 16 位，保留原文件名和画幅尺寸。三个颜色通道使用相同变换，最终彩色图只重采样一次。
- 输入自带的 ICC 配置文件原样保留；输入没有 ICC 时不擅自指定色彩空间。
- 旋转插值会改变像素值，可能轻微软化细节。“保留 16 位”指保留每通道精度，不表示变换前后像素完全相同。
- 配准失败的图片不会混入合格结果。若最终检查未通过，请查看报告并暂勿导入 AS。

1800×1800 的无压缩 RGB16 TIFF 约为 **19.4 MB/张**，4080 张约需 **79.3 GB**，另需报告与余量空间。程序运行期间不要编辑或移动输入。只把 `frames/` 中需要的 TIFF 导入 AS，保留报告和任务文件以便续跑与排查。

### 验证状态

这是初版预览（prerelease），验证范围如下：

- 配准算法的命令行前身已完成一组 **4080 张**实拍月面 TIFF 的处理；这不等于用当前 GUI 再次完整跑过 4080 张。
- GUI 所用引擎对横跨拍摄时段的 **10 张实拍 TIFF** 全部配准通过；该组独立纹理残差中位约 **0.337 像素**，最大剩余旋转约 **0.0119°**。这些数值描述该组测试，不是对任意素材的精度承诺。
- **19 项不创建窗口的自动检查**通过，覆盖核心处理与界面完成状态逻辑；另验证了部分选择、取消续跑、损坏输出重建、已知变换、无效输入拒绝和原片未变化。
- Windows x64 便携 EXE 的无窗口自检、运行库导入、RGB16 TIFF 精确写入读回及刚性变换数值检查通过；交付 ZIP 的完整性和源码指纹已核对。

实际 GUI 点击流程、窗口布局、跨电脑兼容性和全新环境构建仍有待更完整的人工验收。建议先用少量自己的素材检查。详细记录见 [验证记录](docs/VALIDATION.md)，操作摘要见 [快速入门](docs/quick-start.zh-CN.txt)。

### 从源码运行、测试与构建

已测试环境为 **Windows x64、Python 3.10**，使用标准库 Tkinter。依赖版本见 [`requirements.txt`](requirements.txt)。在项目根目录的 PowerShell 中执行：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launch.py
```

运行不创建窗口的回归检查：

```powershell
.\.venv\Scripts\python.exe -m unittest test_engine
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

默认执行 10 项核心检查和 9 项界面逻辑检查；真实素材集成测试默认跳过。可按 [`test_engine.py`](test_engine.py) 文件开头的说明设置 `MOONALIGN_TEST_INPUT`、`MOONALIGN_TEST_OUTPUT`，以及可选的 `MOONALIGN_TEST_REFERENCE` 运行集成测试；测试输出必须使用新目录。

在 Windows x64 上构建便携版：

```powershell
py -3.10 -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.build-venv\Scripts\python.exe build_portable.py
```

构建入口为 [`build_portable.py`](build_portable.py) 和 [`MoonAlign.spec`](MoonAlign.spec)，默认生成 `dist/MoonAlign/` 与 `release/` 中的 ZIP。便携版也支持无窗口运行库自检，在可写目录中执行：

```powershell
.\MoonAlign.exe --self-check self-check.json
```

维护配准算法或隐藏阈值时，需要递增 [`moonalign/engine.py`](moonalign/engine.py) 中的 `ALGORITHM_VERSION`，并使用新任务目录，避免混用检查点。发布文件不包含拍摄原片；实际任务报告可能含本机路径和照片文件名，公开报告前请自行检查。

### 许可

MoonAlign 自有源码采用 [MIT License](LICENSE)。便携版所含 Python、Tcl/Tk、NumPy、OpenCV、Pillow、PyInstaller 等组件各自保留其许可证；详见 [第三方声明](THIRD_PARTY_NOTICES.txt) 和 [`licenses/`](licenses/)。

## English

### What it does

When shooting a lunar sequence from an ordinary tripod, the Moon can rotate between frames even after PIPP has centered it. A single fixed alignment point may leave rotation ghosts around the outer disc after stacking.

MoonAlign aligns each frame's overall orientation and position to one reference image, producing a separate **16-bit RGB TIFF sequence**. It uses lunar texture matching, rigid transforms and independent checks, so frames do not need to be rotated by hand. AutoStakkert! then handles quality ranking, local alignment and stacking.

```text
RAW / NEF → PIPP → MoonAlign → AutoStakkert! → waveSharp / colour processing
                 global alignment    selection, local alignment, stacking
```

PIPP, AutoStakkert! and post-processing tools are separate applications. MoonAlign processes files locally without uploading photographs or requiring an account.

### Quick start

1. Download and fully extract the portable ZIP linked above, then run `MoonAlign.exe`. Keep all files together, including `_internal`; copying the EXE alone is insufficient.
2. In PIPP, decode RAW into **three-channel RGB TIFFs with 16 bits per channel**, center the Moon and use the same crop dimensions throughout. Keep the complete lunar disc and generous black margins. Use consistent white balance and colour settings. Disable monochrome conversion, resizing, sharpening, denoising and per-frame automatic brightness equalization.
3. Choose the TIFF folder in MoonAlign and check all frames or a subset. Both `.tif` and `.tiff` are supported; subfolders are not scanned. For a first run, select a dozen or so frames covering the beginning, middle and end of the sequence, including large rotations.
4. Choose a sharp, complete reference from the selected frames, usually near the middle of the capture period. The default reference is a convenient starting point, not an automatic selection of the sharpest image.
5. Choose a separate output folder and start. A new folder, an existing empty folder, or an existing MoonAlign output for the same job can be used. The program automatically runs a time-spread pilot, processes the full selection if the pilot passes, then checks the outputs.
6. After the checks pass, inspect lunar edges, maria and craters. Import the TIFFs in **`frames/`** into AutoStakkert! Start with a normal-scale stack before deciding whether to try Drizzle.

Cancel stops new work and lets in-flight frames finish safely. Restart with **the same file selection, reference and output folder** to validate checkpoints and resume. Previously passed, unchanged outputs are reused. Use a new output folder when changing the inputs, reference or algorithm version.

### Supported input and limits

| Item | v1.0.0 requirement |
| --- | --- |
| Files | `.tif` / `.tiff` in one folder; three-channel RGB, 16 bits per channel |
| Canvas | Identical dimensions, 800–6000 pixels on each side, normal orientation |
| Moon | A complete, near-full lunar disc; equivalent diameter at least 800 pixels, preferably 1000 or more |
| Margins | Enough black background to accommodate rotation and translation without clipping |
| Capture | One sequence with consistent focal length, teleconverter, resizing and image scale |

The main real-data validation used 1800×1800 TIFFs exported by PIPP, with a lunar diameter of about 1100 pixels. Input is not limited to a particular camera brand. Try a small batch first when changing equipment, dimensions or lunar phase. A Windows file property of “48-bit depth” means 16 bits for each RGB channel; DPI does not affect alignment.

MoonAlign corrects **global rotation and translation** at a fixed scale. It does not apply local warping, stack, sharpen, enhance colour or generate detail. It cannot recover defocus, motion blur, clipped highlights, cloud-obscured detail, missing lunar edges or local atmospheric distortion. Scale changes caused by different focal lengths, resizing factors or teleconverters are outside its scope. Avoid mixing different nights or substantially different lunar phases. Lunar close-ups, thin crescents, eclipses and low-texture images have not been validated with real captures.

Passing the automatic checks is not a guarantee of perfect registration or good image quality. Continue to use quality selection and local alignment in AutoStakkert!

### Outputs and source protection

```text
chosen-output-folder/
├─ frames/                Passed TIFFs with their original filenames
├─ reports/               Summary, CSV and per-frame checks
├─ job_config.json        Job configuration for resuming
├─ source_inventory.json  Input inventory for change detection
└─ quarantine/            Invalid previous outputs, when necessary
```

- Source images are read only and are never rewritten. Input and output directories must not overlap.
- Output is uncompressed RGB TIFF, 16 bits per channel, with the original filenames and canvas dimensions. All colour channels use the same transform; final colour data is resampled only once.
- An existing input ICC profile is preserved exactly. No colour space is assigned if the input has no ICC profile.
- Rotation interpolation changes pixel values and can soften fine detail slightly. Keeping 16-bit precision does not mean the transformed pixels remain identical to the originals.
- Failed frames are excluded from the passed sequence. If the final checks fail, review the reports before importing into AS.

An uncompressed 1800×1800 RGB16 TIFF is about **19.4 MB**; 4080 frames need approximately **79.3 GB**, plus reports and working headroom. Do not edit or move inputs while a job is running. Import only the desired TIFFs from `frames/` into AS, and keep the job files and reports for resuming and troubleshooting.

### Validation status

This is an initial preview (prerelease), with the following validation scope:

- The command-line predecessor of the registration algorithm processed a real **4080-frame** lunar TIFF sequence. The full sequence has not been rerun through the current GUI version.
- The GUI's engine passed **10 real TIFFs** spread across the capture period. This test had a median independent texture residual of approximately **0.337 pixels**, with a maximum remaining rotation of approximately **0.0119°**. These measurements describe that dataset, not a promised accuracy for arbitrary inputs.
- **19 automated checks without creating a window** passed, covering core processing and GUI completion-state logic. Additional checks covered partial selection, cancellation and resume, rebuilding a damaged output, known transforms, invalid-input rejection and unchanged sources.
- The Windows x64 portable EXE passed a windowless runtime self-check, dependency imports, an exact RGB16 TIFF write/read round trip and rigid-transform numerical checks. Release ZIP integrity and application source fingerprints were verified.

The actual GUI click-through workflow, window layout, compatibility across different computers and a build in a newly provisioned environment still need broader manual validation. Start with a small selection of your own frames. See the bilingual [validation record](docs/VALIDATION.md) and the [quick-start guide](docs/quick-start.zh-CN.txt), currently in Chinese.

### Run, test and build from source

The tested environment is **Windows x64 with Python 3.10**, using the standard-library Tkinter interface. Pinned dependencies are in [`requirements.txt`](requirements.txt). Run these commands in PowerShell from the repository root:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launch.py
```

Run the checks that do not create a window:

```powershell
.\.venv\Scripts\python.exe -m unittest test_engine
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

By default these run 10 core checks and 9 GUI logic checks; the real-data integration test is skipped. To enable it, follow the header of [`test_engine.py`](test_engine.py) and set `MOONALIGN_TEST_INPUT`, `MOONALIGN_TEST_OUTPUT`, and optionally `MOONALIGN_TEST_REFERENCE`. The integration output must be a new directory.

Build the portable edition on Windows x64:

```powershell
py -3.10 -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.build-venv\Scripts\python.exe build_portable.py
```

The build uses [`build_portable.py`](build_portable.py) and [`MoonAlign.spec`](MoonAlign.spec). Defaults produce `dist/MoonAlign/` and ZIP archives under `release/`. The portable EXE also offers a windowless runtime self-check; run it from a writable directory:

```powershell
.\MoonAlign.exe --self-check self-check.json
```

When changing the registration algorithm or hidden thresholds, increment `ALGORITHM_VERSION` in [`moonalign/engine.py`](moonalign/engine.py) and use a new job directory to avoid mixing checkpoints. No source photographs are included in the release. Real job reports may contain local paths and photograph filenames; review them before sharing publicly.

### License

MoonAlign's own source is released under the [MIT License](LICENSE). Bundled components, including Python, Tcl/Tk, NumPy, OpenCV, Pillow and PyInstaller, retain their respective licenses. See [third-party notices](THIRD_PARTY_NOTICES.txt) and [`licenses/`](licenses/).
