# Image Translator

<p align="center">
  <a href="#chinese-version">中文</a> | <a href="#english-version">English</a>
</p>

<a name="chinese-version"></a>

## 下载与安装

### 方式一：直接下载可执行文件（推荐）

1. 前往 [Releases](../../releases) 页面下载最新版本的 `ImageTranslator.exe`
2. 双击运行即可，无需安装 Python 或任何依赖
3. 首次运行会在 `C:\Users\<用户名>\AppData\Roaming\ImageTranslator` 创建配置文件

### 方式二：从源码运行（开发者）

<details>
<summary>点击展开源码运行说明</summary>

1. **环境要求**: Python 3.10 或更高版本
2. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```
3. **启动程序**:
   ```bash
   python src/main.py
   ```

</details>

## 配置说明

首次运行需在 **设置 → API及代理设置** 中配置：

- **推荐使用 Gemini**：免费、快速、准确
- **API Key 获取**：[Google AI Studio](https://aistudio.google.com/)
- **代理设置**：如无法访问 Google 服务，请配置 HTTP 代理（例如 `127.0.0.1:7890`）

支持的 LLM Provider：
- Gemini（推荐）
- OpenAI Compatible（支持 OpenAI、Claude、DeepSeek 等）

## 功能特性

- **智能 OCR 与翻译**：基于大语言模型的文字识别与翻译
- **可视化编辑器**：
  - 选中、移动、缩放、旋转文本块
  - 自定义字体、颜色、描边、背景色
  - 调整行间距、字间距等细节
- **批量处理**：一次性翻译多张图片并导出
- **术语表支持**：固定特定词汇的翻译，保持一致性
- **精确定位**：优化的 Prompt 确保文本框位置准确

<details>
<summary><strong>效果展示 (点击展开)</strong></summary>

![示例图片 4](sample/4.png)
![示例图片 3](sample/3.png)
![示例图片 2](sample/2.png)
![示例图片 1](sample/1.png)
</details>

## 使用说明

1. **载入图片**：文件 → 载入图片
2. **翻译**：点击"翻译当前图片"按钮
3. **编辑**：
   - 点击文本块进行选择
   - 拖动移动位置
   - 拖动角落缩放大小
   - 拖动顶部圆点旋转角度
   - 右侧面板可编辑译文和调整样式
4. **导出**：点击"导出翻译结果"保存图片

## 常见问题

<details>
<summary>配置文件保存在哪里？</summary>

配置文件保存在：`C:\Users\<用户名>\AppData\Roaming\ImageTranslator\config.ini`

可以直接删除此文件夹来重置所有设置。
</details>

<details>
<summary>如何更换程序图标？</summary>

如果您从源码构建，可以：
1. 准备 `.ico` 格式的图标文件
2. 修改 `ImageTranslator.spec` 中的 `icon='icon.ico'`
3. 运行 `pyinstaller ImageTranslator.spec` 重新打包
</details>

<details>
<summary>支持哪些语言？</summary>

理论上支持所有语言互译，常见组合：
- 日语 → 中文
- 英语 → 中文
- 韩语 → 中文
- 等等...

在设置中可以自定义源语言和目标语言。
</details>

## 贡献

欢迎提交 Issue 和 Pull Request。

## 开源协议

本项目采用 MIT 协议开源。

---

<a name="english-version"></a>
<details>
<summary>English Version</summary>

<br>

## Download & Installation

### Method 1: Download Executable (Recommended)

1. Go to [Releases](../../releases) page and download the latest `ImageTranslator.exe`
2. Double-click to run - no Python or dependencies required
3. Configuration file will be created at `C:\Users\<username>\AppData\Roaming\ImageTranslator` on first run

### Method 2: Run from Source (Developers)

<details>
<summary>Click to expand source code instructions</summary>

1. **Prerequisites**: Python 3.10 or higher
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run Application**:
   ```bash
   python src/main.py
   ```

</details>

## Configuration

Configure in **Settings → API & Proxy Settings** on first launch:

- **Recommended: Gemini** - Free, fast, and accurate
- **Get API Key**: [Google AI Studio](https://aistudio.google.com/)
- **Proxy**: Configure HTTP proxy if needed (e.g., `127.0.0.1:7890`)

Supported LLM Providers:
- Gemini (Recommended)
- OpenAI Compatible (Supports OpenAI, Claude, DeepSeek, etc.)

## Features

- **Smart OCR & Translation**: Powered by large language models
- **Visual Editor**:
  - Select, move, resize, and rotate text blocks
  - Customize fonts, colors, outlines, backgrounds
  - Adjust line spacing, character spacing, etc.
- **Batch Processing**: Translate multiple images at once
- **Glossary Support**: Maintain consistent translations
- **Precise Positioning**: Optimized prompts for accurate text box placement

<details>
<summary><strong>Sample Images (Click to expand)</strong></summary>

![Sample Image 4](sample/4.png)
![Sample Image 3](sample/3.png)
![Sample Image 2](sample/2.png)
![Sample Image 1](sample/1.png)
</details>

## Usage

1. **Load Image**: File → Load Image
2. **Translate**: Click "Translate Current Image"
3. **Edit**:
   - Click text blocks to select
   - Drag to move
   - Drag corners to resize
   - Drag top circle to rotate
   - Edit translation and styles in right panel
4. **Export**: Click "Export Translation Result"

## FAQ

<details>
<summary>Where is the config file saved?</summary>

Config file location: `C:\Users\<username>\AppData\Roaming\ImageTranslator\config.ini`

You can delete this folder to reset all settings.
</details>

<details>
<summary>Which languages are supported?</summary>

Theoretically supports all language pairs, common combinations:
- Japanese → Chinese
- English → Chinese
- Korean → Chinese
- etc.

You can customize source and target languages in settings.
</details>

## Contributing

Issues and Pull Requests are welcome.

## License

This project is licensed under the MIT License.

</details>
