# 数字人视频生成方案对比：三大商业 API + 开源自部署

> 整理日期：2026 年 7 月 7 日（更新：新增 LongCat-Video-Avatar 1.5 开源方案）
> 涵盖方案:HeyGen、可灵(Kling)、OmniHuman-1.5(火山引擎即梦AI)、LongCat-Video-Avatar 1.5(开源自部署)
> 注:价格与政策可能随时调整,下单前请以官方页面为准。

---

## 一、方案总览

| 对比项 | HeyGen API | 可灵 API | OmniHuman-1.5 API | LongCat-Avatar 1.5(开源) |
|---|---|---|---|---|
| 出品方 | HeyGen(海外) | 快手 | 字节跳动 | 美团 |
| 获取方式 | heygen.com/api-pricing | klingai.com/global/dev | volcengine.com(控制台 → 即梦AI) | GitHub / HuggingFace 免费下载 |
| 文档 | docs.heygen.com | klingai.com/document-api | volcengine.com/docs/85621 | github.com/meituan-longcat/LongCat-Video |
| 计费模式 | 按量付费(Pay-As-You-Go),$5 起充 | 预付资源包(credits),在线下单 | 火山引擎资源包 / 按量付费 | 免费(自备 GPU,MIT 协议) |
| 参考单价 | 标准数字人约 $1/分钟;Avatar IV 约 $4/分钟(1080p) | O1 模型约 0.6–1.2 元/秒(约 36–72 元/分钟) | 按即梦AI视频生成计费说明,随分辨率/时长浮动 | 零边际成本(电费/折旧) |
| 免费额度 | 无(2026 年 2 月起取消) | 会员/活动性质的测试额度 | 新用户通常有试用额度 | 完全免费 |
| 支付/门槛 | 国际信用卡(Visa/Mastercard) | 国内支付,需实名/企业认证 | 国内支付,需火山引擎实名认证 | 需 48GB 级 GPU(int8+蒸馏单卡可跑) |
| 并发限制 | 最多 10 个任务同时处理 | 按资源包/账户等级 | 按火山引擎账户配额 | 取决于自有卡数 |
| 失败扣费 | 按实际生成秒数计费 | 失败任务(含审核失败)不扣 credits | 以官方计费说明为准 | 不涉及 |

---

## 二、各方案购买流程

### 方案一:HeyGen API(海外,综合易用性最好)

**官方地址**
- 购买/充值:https://www.heygen.com/api-pricing
- 开发文档:https://docs.heygen.com

**购买步骤**
1. 注册 HeyGen 账号(无需购买 Creator/Pro 等网页版套餐,API 独立计费)
2. 进入 Dashboard → Settings → API,生成 API key
3. 给 API 钱包充值,最低 $5 起,用多少扣多少
4. 调用时通过 `X-Api-Key` 请求头传入密钥

**计费标准**
- 基准:1 美元 ≈ 1 分钟 720p/1080p 标准数字人视频
- Avatar IV:$4/分钟(1080p),4K 更高
- 视频翻译:约 $2/分钟(按源视频时长)
- Video Agent:$2/分钟
- 按实际生成秒数扣费,非按提交任务数

**注意事项**
- 2026 年 2 月起无免费 API 额度,测试也需先小额充值
- 充值额度自购买起 12 个月后过期
- API 余额与网页版套餐积分是两个独立池子,不互通
- Digital Twin 创建 API、校对 API 仅企业版(Enterprise)开放
- 国内使用需考虑网络访问与合成内容标识合规要求

---

### 方案二:可灵 API(画质标杆,国内直接购买)

**官方地址**
- 开发者平台:https://klingai.com/global/dev
- API 文档:https://klingai.com/document-api
- 国内网页版体验:https://klingai.kuaishou.com

**购买步骤**
1. 注册可灵开放平台账号,完成实名认证(企业用途建议企业认证)
2. 在线购买预付资源包(credits)
3. 后台创建 AccessKey / SecretKey
4. 按 API 文档调用;数字人、对口型、语音合成等为独立接口

**计费标准**
- 可灵 O1:标准模式约 0.6–0.9 元/秒,高品质模式约 0.8–1.2 元/秒
- 可灵 2.6 图生视频 10 秒约 5–10 元(带声音/指定音色更高)
- 同一接口在不同参数(模式、时长、音频)下费用可能相差数倍
- 实际扣费以后台资源包记录与任务记录中的 final_unit_deduction 为准

**注意事项**
- 失败任务不扣 credits(含内容审核失败)
- 三个方案中单价最高,适合少量高要求成片
- 存在第三方聚合平台转售(约官网 8 折),但稳定性与合规责任依赖中间商,正式用途建议走官方渠道

---

### 方案三:OmniHuman-1.5 API(字节生态,走火山引擎)

**官方地址**
- 火山引擎控制台:https://www.volcengine.com
- 即梦AI 文档:https://www.volcengine.com/docs/85621(即梦AI-视频生成/数字人板块)
- 海外结算渠道:BytePlus

**购买步骤**
1. 注册火山引擎账号并完成实名认证
2. 控制台开通「即梦AI」服务,购买资源包或选择按量付费
3. 获取 AK/SK 密钥
4. 按数字人视频生成文档调用(异步模式:提交任务 → 轮询结果)

**计费标准**
- 按即梦AI视频生成计费说明执行,随分辨率、时长等参数浮动
- 新用户通常有试用额度,可先跑通链路再充值

**注意事项**
- OmniHuman 不单独售卖,即梦AI/火山引擎是唯一官方通道
- 社区有开源调用参考项目(omnihuman-api),涵盖容器化部署、密钥管理、异步任务队列等生产化实践
- 国内网络与合规链路最顺,适合国内批量生产环境

---

### 方案四:LongCat-Video-Avatar 1.5(开源自部署,零 API 费用)【新增】

**官方地址**
- GitHub:https://github.com/meituan-longcat/LongCat-Video
- HuggingFace:https://huggingface.co/meituan-longcat/LongCat-Video-Avatar-1.5
- ModelScope:https://www.modelscope.cn/models/meituan-longcat/LongCat-Video-Avatar-1.5
- 技术报告:GitHub 仓库 assets 目录下 LongCat-Video-Avatar-1.5-Tech-Report.pdf

**项目概况**
- 美团 LongCat 团队 2026 年 5 月开源,基于 13.6B 参数的 LongCat-Video 基座(文生视频/图生视频/视频续写统一架构)
- Avatar 1.5 原生支持音频-文本生视频(AT2V)、音频-文本-图片生视频(ATI2V)和视频续写,兼容单路/多路音频
- 音频编码器采用 Whisper-Large,DMD 蒸馏至 8 步推理(约 15 倍提速),GRPO 帧级偏好对齐
- 支持多人对话(区分说话者/聆听者)、动漫/动物等风格化主体、长视频稳定生成
- **MIT 协议**(含模型权重),商用最友好

**官方评测(注意为厂商自评,需自行验证)**
- 用户偏好盲测:对可灵 Avatar 2.0 胜率 65.9%,对 OmniHuman-1.5 胜率 61.1%,对 HeyGen 胜率 54.3%
- 单人场景得分 3.336,高于 HeyGen 与 OmniHuman-1.5;多人场景 2.730,领先 InfiniteTalk(2.339)
- 评测基准覆盖新闻播报、知识教育、日常、娱乐、唱歌、商业推广 6 类场景,中英双语

**部署要求(适配 4×A40 服务器)**
- 环境:PyTorch 2.6 + CUDA 12.4,A40(Ampere)完全兼容
- 官方支持 torchrun 多卡 context parallel(--context_parallel_size 参数)、--use_distill 蒸馏加速、--use_int8 量化
- int8 + 8 步蒸馏下单卡 48GB 可独立运行,支持 4 路并发量产;4 卡并行可加速长视频生成
- 成本:仅电费与折旧,无按量 API 费用

**注意事项**
- 2026 年 5 月新发布,社区生态(ComfyUI 工作流等)不如 Wan/Hunyuan 系成熟
- 胜过商业系统的结论来自美团自建基准,正式采用前务必用自己的素材做横向测试
- 官方调参建议:Audio CFG 3–5 之间口型同步最佳;提示词越详细一致性越好;ref_img_index 参数可调节动作重复问题

---

## 三、选择建议

结合「课程口播为主 + 4×A40 自部署为主力产能」的场景:

| 需求 | 推荐方案 | 理由 |
|---|---|---|
| 快速验证 / 英文内容 | HeyGen | 单价最低、接入最简单、英文口型效果好 |
| 中文高画质标杆 | 可灵 | 专业盲测领先,用少量额度对比自部署效果 |
| 情绪表达 / 双人对话 | OmniHuman-1.5 | 情感感知与多角色能力突出,国内链路顺畅 |
| 批量量产 / 长视频课程口播 | **自部署 LongCat-Avatar 1.5(首选)** | 官方人评超越商业系统,原生多卡并行,长视频稳定,MIT 协议,零 API 成本 |
| 轻量对照 / 低门槛出片 | 自部署 EchoMimic V3 / HeyGem | 1.3B 轻量模型,单卡即可 4 路并发,适合作为效果基线 |

**实操建议**:
1. 先在单卡 A40 上以 int8 + 蒸馏模式跑通 LongCat-Avatar 1.5,用真实课程音频出样片
2. 三家商业 API 各充最小额度,用同一段音频做横向测试(口型精度、动作自然度、生成速度、单分钟成本)
3. 若 LongCat 效果达标,量产走 4×A40 本地部署(单条长视频用 4 卡并行,批量短视频用 4 路单卡并发);API 留作效果标杆与应急产能
4. 每隔一个季度重新评估:该领域迭代极快,开源与商业的排名随时可能变化

---

## 附:合规提醒

在国内正式发布 AI 生成的数字人内容,需遵守《互联网信息服务深度合成管理规定》等要求,对合成内容进行显著标识;涉及真人形象克隆时,需取得本人授权。
