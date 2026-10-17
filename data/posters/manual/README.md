# 手动发布图片海报

1. 在 GitHub 上打开本目录，点 **Add file → Upload files**，上传 PNG 或 JPG 并提交到 `main`。
2. 打开 **Actions → Set displayed posters → Run workflow**。
3. 在 `filenames` 填写要展示的文件名，用英文逗号分隔，例如 `2610.17559.png,2609.30441.png`；不填则撤下所有手动海报。
4. 用 `include_generated` 勾选是否同时展示本周自动生成的海报。

文件名请包含 arXiv 号，以便对应论文卡片找到海报。运行成功后，所选图片会出现在海报轮换中；取消选择不会删除图片。手动海报优先于同一论文的自动生成版，所选列表会在后续自动更新时保留。
