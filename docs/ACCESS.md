# ACCESS — 让 newswiki.cn 在受限网络下也能打开

> 面向的问题：**HR 点开简历里的链接，页面打不开。**
> 这份文档记录已经在代码里做掉的事、以及需要人工提交的事（我做不了——这些入口要么需要登录，要么需要邮箱验证）。

---

## 1. 风险来自哪里

| 风险 | 说明 | 现状 |
|---|---|---|
| **企业 URL 过滤按「未分类域名」阻断** | `newswiki.cn` 是 2026 年新注册的域名，在 Zscaler / Netskope / Palo Alto / Fortinet 等厂商的分类库里大概率还是 `Uncategorized` 或 `Newly Registered Domain`。不少外企的默认策略就是直接拒绝这两类。 | **最大风险，需人工提交分类申请**，见 §3 |
| **首屏依赖境外第三方资源** | 原先 `index.html` 用渲染阻塞的 `<link>` 从 `fonts.googleapis.com` 拉字体，`/api/v1/docs/` 从 `cdn.jsdelivr.net` 拉 Swagger UI。前者在中国大陆不可达 → 国内访客白屏到超时。 | **已修**，见 §2 |
| **禁用 JavaScript 的受限浏览器** | SPA 在无 JS 环境下只有一个空 `<div>`。 | **已修**：`index.html` 里加了 `<noscript>` 兜底内容 |
| `.cn` 顶级域被整体拉黑 | 少数高度保守的策略会按 TLD 拉黑。 | 无法从技术侧解决。缓解手段是简历里同时给出 GitHub 仓库链接 |
| 首尔 Aliyun IP 段的信誉 | 云 VPS 段常带扫描流量，可能出现在个别威胁情报源里。 | 用 §4 的工具自查；目前未发现命中 |

---

## 2. 已在代码里做掉的（本次变更）

- **字体自托管**：`@fontsource-variable/fraunces` + `@fontsource/ibm-plex-{sans,mono}`，在 `frontend/src/main.ts` 里 import，只引 Latin 子集。`index.html` 里的 Google Fonts `<link>` 和两条 `preconnect` 已删除。
- **Swagger UI 自托管**：`drf-spectacular-sidecar` + `SWAGGER_UI_DIST: "SIDECAR"`，资源随版本锁定，走 whitenoise 提供。
- **可被抓取、可被分类**：`index.html` 补了 `description` / Open Graph / `canonical`，新增 `public/robots.txt` 与 `public/sitemap.xml`。被搜索引擎正常收录是 URL 过滤厂商给出分类的主要依据之一。
- **`<noscript>` 兜底**：无 JS 时展示项目简介 + GitHub 链接 + API 文档链接。

**验证方式**（部署后）：

```bash
curl -s https://newswiki.cn/ | grep -c fonts.googleapis.com     # 期望 0
curl -s https://newswiki.cn/api/v1/docs/ | grep -c jsdelivr     # 期望 0
```

---

## 3. 需要人工提交的分类申请

> 这些入口需要人工填表/邮箱验证，我无法代为提交。
> 建议统一提交为 **`Technology` / `Computers & Internet` / `Information Technology`** 类别，说明写：个人技术作品集网站，展示一个 AI 资讯知识库的全栈实现，无用户数据、无交易、无广告。
> 下面的地址是撰写本文时可用的入口，厂商偶尔会改版；打不开时搜「<厂商名> URL categorization request」。

| 厂商 | 提交入口 | 备注 |
|---|---|---|
| Zscaler | `https://sitereview.zscaler.com/` | 外企用得最多的一家，**优先提交** |
| Palo Alto Networks | `https://urlfiltering.paloaltonetworks.com/` | 查询后页面上有 "Request Change" |
| Netskope | `https://urllookup.netskope.com/` | |
| Fortinet FortiGuard | `https://www.fortiguard.com/webfilter` | 查询后可提交 "Request Reclassification" |
| Symantec / Broadcom | `https://sitereview.bluecoat.com/` | 老牌 BlueCoat 分类库，覆盖面广 |
| Trellix (原 McAfee) | `https://trustedsource.org/` | |
| Forcepoint | `https://csi.forcepoint.com/` | |
| Cisco Talos | `https://talosintelligence.com/reputation_center/` | 查 `newswiki.cn` 的信誉，异常时走页面上的申诉 |
| Cisco Umbrella / OpenDNS | `https://domain.opendns.com/newswiki.cn` | |

**提交后的预期**：人工审核，一般数天到两周生效，且**不保证所有企业策略都会放行**——有的公司即便域名已分类，仍会对整个 `.cn` 或「个人网站」类别拦截。这一条要如实认知，不要以为提交完就万事大吉。

---

## 4. 自查清单

```bash
# 恶意软件/钓鱼标记（应为 "No unsafe content found"）
#   https://transparencyreport.google.com/safe-browsing/search?url=newswiki.cn
# 多引擎信誉
#   https://www.virustotal.com/gui/domain/newswiki.cn
# 全国各省实际可达性与延迟
#   https://www.itdog.cn/http/  （D12 实测：290 个监测点 100% 成功，平均 0.712s）

# 证书链
echo | openssl s_client -connect newswiki.cn:443 2>/dev/null | openssl x509 -noout -dates -issuer
```

---

## 5. 兜底：简历里放两个链接

技术手段无法覆盖所有企业策略。简历与求职信里建议同时给出：

1. **在线演示**：`https://newswiki.cn`
2. **源码仓库**：`https://github.com/t956175001/news-wiki` — README 里有演示 GIF、30 秒视频和四张核心截图，**打不开演示站也能看懂这个项目做了什么**

`github.com` 在企业网和国内基本都放行，这是成本最低、最可靠的兜底。

---

## 6. 明确没有做的

- **静态镜像站**（GitHub Pages / Cloudflare Pages 上跑一份只读快照）：能绕开域名分类问题，但要新增一套 API 快照导出与构建流程。当前判断是「README 已经能承担兜底职责」，性价比不够。若日后确认有 HR 反馈打不开，这是第一优先要补的。
- **把 DNS 迁到 Cloudflare 走代理**：与 ADR-006 / ADR-007 的结论冲突（D12 的 ITDOG 实测数据不支持引入 CDN），且会引入新的境外依赖。
