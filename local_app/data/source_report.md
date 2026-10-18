# 数据来源与边界

公开演示：项目自编16条模拟评论，虚构型号“回声 AF4”。它们不是消费者研究数据，不来自 Amazon，不是 Amazon 评论的改写。逐条提取通过真实模型接口执行，随后以程序归并主题、去重计数及生成有依据的行动方向；访客加载的是预置结果，不现场调用模型。

本地研究：曾使用 McAuley Lab / UC San Diego 发布的 Amazon Reviews 2023，按确切 ASIN B07FDJMC9Q 筛选 Ninja AF101。原50条与新增25条开发验证分开保存，不在此仓库或站点内置原文、模型输出、研究报告或真实评论截图。研究采样不是随机抽样，不能代表全部消费者。

发布方说明不能为评论文本授予许可，主要为研究提供数据；对非商业论文使用无异议的回复不等于公开原文展示、再分发或商业用途许可。删除用户名也不解决文本使用范围问题。本地模型处理已由使用者授权，但这不代表权利问题已全面解决。部署者应仅上传自己有权使用的数据。

- 项目：https://amazon-reviews-2023.github.io/main.html
- 原始仓库：https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023
- 发布方许可说明：https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/discussions/1
- 固定源版本：2b6d039ed471f2ba5fd2acb718bf33b0a7e5598e

许可说明复核日期：2026-10-18。Best Buy 评论未纳入。源码与模拟演示的可访问性不代表对第三方评论拥有再许可权。
