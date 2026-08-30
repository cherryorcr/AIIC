# TechMatch AI 面试陪练前端

这是面试陪练平台的本地前端 MVP，使用 React、TypeScript、Vite 和 lucide-react。

## 本机运行

```bash
npm install
npm run dev
```

打开 http://localhost:5173/。

页面已通过 `/api` 接入 FastAPI，覆盖总览、场景化训练、算法题代码运行、岗位匹配、题库、训练报告和系统设置。后端不可用时保留少量演示题作为降级显示；模型密钥只在后端环境变量中配置，不进入浏览器。

## 容器运行

```bash
docker build -t techmatch-frontend .
docker run --rm -p 8080:80 techmatch-frontend
```

Nginx 已配置 SPA 路由回退和 `/api/` 反向代理，默认后端服务名为 `backend`、端口为 `8000`。
