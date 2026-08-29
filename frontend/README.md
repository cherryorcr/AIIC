# TechMatch AI 面试陪练前端

这是面试陪练平台的本地前端 MVP，使用 React、TypeScript、Vite 和 lucide-react。

## 本机运行

```bash
npm install
npm run dev
```

打开 http://localhost:5173/。

当前页面使用本地 mock 数据，已覆盖：总览、场景化训练、算法题代码运行、岗位匹配、题库、训练报告和系统设置。后续接入 FastAPI 时，前端只需将请求指向 `/api`，不需要把模型密钥放到浏览器。

## 容器运行

```bash
docker build -t techmatch-frontend .
docker run --rm -p 8080:80 techmatch-frontend
```

Nginx 已配置 SPA 路由回退和 `/api/` 反向代理，默认后端服务名为 `backend`、端口为 `8000`。
