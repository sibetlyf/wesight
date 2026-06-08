# 企业官网部署文档

## 部署包说明

本部署包包含企业官网的完整生产环境静态资源文件，适用于 Nginx、Apache 或静态托管服务部署。

**部署包文件**: `ai-company-website-deployment.zip`

## 文件结构

```
dist/
├── index.html              # 主入口 HTML
└── assets/
    ├── *.css               # 样式文件（含所有页面样式）
    └── *.js                # JavaScript 文件（含 Vue 运行时）
```

### 构建输出清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `index.html` | HTML | 主入口页面 |
| `assets/index-*.js` | JavaScript | Vue 应用主 bundle |
| `assets/index-*.css` | CSS | 全局样式 |
| `assets/Home-*.js/css` | JS/CSS | 首页组件 |
| `assets/About-*.js/css` | JS/CSS | 关于我们页面 |
| `assets/Services-*.js/css` | JS/CSS | 产品服务页面 |
| `assets/Team-*.js/css` | JS/CSS | 技术团队页面 |
| `assets/News-*.js/css` | JS/CSS | 新闻动态页面 |
| `assets/Contact-*.js/css` | JS/CSS | 联系我们页面 |
| `assets/Footer-*.js/css` | JS/CSS | 页脚组件 |

---

## 部署方式

### 方式一：Nginx 部署

#### 1. 安装 Nginx

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install nginx

# CentOS/RHEL
sudo yum install nginx

# macOS
brew install nginx
```

#### 2. 配置 Nginx

创建站点配置文件 `/etc/nginx/sites-available/your-domain.conf`:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    root /var/www/ai-company-website;
    index index.html;

    # 启用 Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied expired no-cache no-store private auth;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml application/javascript application/json;
    gzip_disable "MSIE [1-6]\.";

    # Vue Router 历史模式支持
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 静态资源缓存 - CSS/JS
    location ~* \.(css|js)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # 静态资源缓存 - 图片/字体
    location ~* \.(jpg|jpeg|png|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # 禁止访问隐藏文件
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
}
```

#### 3. 上传并部署

```bash
# 解压部署包
unzip ai-company-website-deployment.zip

# 创建网站目录
sudo mkdir -p /var/www/ai-company-website

# 复制文件
sudo cp -r dist/* /var/www/ai-company-website/

# 设置权限
sudo chown -R www-data:www-data /var/www/ai-company-website
sudo chmod -R 755 /var/www/ai-company-website

# 启用站点
sudo ln -s /etc/nginx/sites-available/your-domain.conf /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
```

---

### 方式二：Apache 部署

#### 1. 安装 Apache

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install apache2

# CentOS/RHEL
sudo yum install httpd

# macOS
brew install httpd
```

#### 2. 配置 Apache

在站点根目录创建 `.htaccess` 文件:

```apache
<IfModule mod_rewrite.c>
  RewriteEngine On
  RewriteBase /
  RewriteRule ^index\.html$ - [L]
  RewriteCond %{REQUEST_FILENAME} !-f
  RewriteCond %{REQUEST_FILENAME} !-d
  RewriteRule . /index.html [L]
</IfModule>

# 启用压缩
<IfModule mod_deflate.c>
  AddOutputFilterByType DEFLATE text/html text/plain text/css application/javascript application/json
</IfModule>

# 静态资源缓存
<IfModule mod_expires.c>
  ExpiresActive On
  ExpiresByType text/css "access plus 1 year"
  ExpiresByType application/javascript "access plus 1 year"
  ExpiresByType application/json "access plus 1 year"
  ExpiresByType image/png "access plus 1 year"
  ExpiresByType image/jpeg "access plus 1 year"
  ExpiresByType image/gif "access plus 1 year"
  ExpiresByType image/svg+xml "access plus 1 year"
  ExpiresByType font/woff2 "access plus 1 year"
</IfModule>

# 安全头
<IfModule mod_headers.c>
  Header set X-Frame-Options "SAMEORIGIN"
  Header set X-Content-Type-Options "nosniff"
  Header set X-XSS-Protection "1; mode=block"
</IfModule>
```

#### 3. 上传并部署

```bash
# 解压部署包
unzip ai-company-website-deployment.zip

# 创建网站目录
sudo mkdir -p /var/www/html/ai-company-website

# 复制文件
sudo cp -r dist/* /var/www/html/ai-company-website/

# 设置权限
sudo chown -R www-data:www-data /var/www/html/ai-company-website
sudo chmod -R 755 /var/www/html/ai-company-website

# 启用 mod_rewrite (如未启用)
sudo a2enmod rewrite
sudo a2enmod deflate
sudo a2enmod expires
sudo a2enmod headers

# 重启 Apache
sudo systemctl restart apache2
```

---

### 方式三：Vercel 部署

#### 方法 A: 使用 Vercel CLI

```bash
# 安装 Vercel CLI
npm install -g vercel

# 解压部署包
unzip ai-company-website-deployment.zip

# 登录 Vercel
vercel login

# 部署
cd dist
vercel --prod
```

#### 方法 B: 使用 Vercel 网页界面

1. 访问 [vercel.com](https://vercel.com)
2. 点击 "Add New Project"
3. 选择 "Deploy from local file" 或直接拖拽 `dist` 文件夹
4. Vercel 会自动检测为静态网站并部署
5. 部署完成后会生成一个 `*.vercel.app` 域名

#### Vercel 配置（可选）

创建 `vercel.json` 进行高级配置:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "**/*",
      "use": "@vercel/static"
    }
  ],
  "routes": [
    {
      "src": "/[^.]+",
      "dest": "/index.html"
    }
  ]
}
```

---

### 方式四：Netlify 部署

#### 方法 A: 使用 Netlify CLI

```bash
# 安装 Netlify CLI
npm install -g netlify-cli

# 解压部署包
unzip ai-company-website-deployment.zip

# 登录 Netlify
netlify login

# 部署
netlify deploy --prod --dir=dist
```

#### 方法 B: 使用 Netlify 网页界面

1. 访问 [netlify.com](https://netlify.com)
2. 登录或注册账号
3. 点击 "Add new site" > "Deploy manually"
4. 拖拽 `dist` 文件夹到部署区域
5. 部署完成后会生成一个 `*.netlify.app` 域名

#### Netlify 配置（可选）

创建 `netlify.toml`:

```toml
[build]
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "SAMEORIGIN"
    X-XSS-Protection = "1; mode=block"
    X-Content-Type-Options = "nosniff"

[[headers]]
  for = "/assets/*"
  [headers.values]
    Cache-Control = "public, max-age=31536000, immutable"
```

---

### 方式五：GitHub Pages 部署

#### 方法 A: 使用 gh-pages 包

```bash
# 安装 gh-pages
npm install -g gh-pages

# 解压部署包
unzip ai-company-website-deployment.zip

# 部署到 gh-pages 分支
gh-pages -d dist
```

#### 方法 B: 手动部署

1. 创建新的 Git 仓库或进入现有仓库
2. 将 `dist` 目录内容复制到仓库根目录或 `docs` 目录
3. 推送代码:

```bash
git add .
git commit -m "Deploy website"
git push origin main
```

4. 进入仓库 Settings > Pages
5. 选择源分支（`main` 根目录 或 `gh-pages` 分支）
6. 等待部署完成，会生成 `https://username.github.io/repo-name` 域名

#### 自定义域名

在仓库根目录创建 `CNAME` 文件:

```
your-domain.com
```

然后在域名提供商处配置 DNS:
- **A 记录**: 指向 `185.199.108.153` (GitHub Pages IP)
- **CNAME 记录**: 指向 `username.github.io`

---

### 方式六：Cloudflare Pages 部署

#### 方法 A: 使用 Wrangler CLI

```bash
# 安装 Wrangler
npm install -g wrangler

# 登录 Cloudflare
wrangler login

# 解压部署包
unzip ai-company-website-deployment.zip

# 部署
wrangler pages deploy dist --project-name=your-project
```

#### 方法 B: 使用 Cloudflare 网页界面

1. 访问 [Cloudflare Dashboard](https://dash.cloudflare.com)
2. 进入 "Workers & Pages"
3. 点击 "Create application" > "Pages"
4. 选择 "Direct upload" 或连接 Git 仓库
5. 上传 `dist` 文件夹内容
6. 部署完成后会生成 `*.pages.dev` 域名

---

## 环境变量设置

本网站为纯静态网站，通常无需后端服务。如需配置 API 地址等：

### 方案一：构建时配置（需要源代码）

```bash
# 创建 .env 文件
echo "VITE_API_URL=https://api.your-domain.com" > .env
echo "VITE_APP_TITLE=企业官网" >> .env

# 重新构建
npm run build
```

### 方案二：运行时配置（推荐）

在 `index.html` 的 `<head>` 中添加全局配置脚本:

```html
<script>
  window.APP_CONFIG = {
    apiUrl: 'https://api.your-domain.com',
    apiTimeout: 30000,
    enableAnalytics: true,
    // 其他配置项...
  };
</script>
```

然后在 Vue 组件中使用:

```javascript
const config = window.APP_CONFIG;
const apiUrl = config.apiUrl;
```

---

## SSL 证书配置

### 方案一：Let's Encrypt（免费，推荐）

```bash
# 安装 Certbot
sudo apt-get install certbot python3-certbot-nginx  # Nginx
sudo apt-get install certbot python3-certbot-apache # Apache

# 获取并安装证书
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
sudo certbot --apache -d your-domain.com -d www.your-domain.com

# 自动续期（已自动配置）
sudo certbot renew --dry-run  # 测试续期
```

### 方案二：Nginx SSL 配置示例

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL 证书路径
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    root /var/www/ai-company-website;
    index index.html;

    # 其他配置...
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### 方案三：云服务商 SSL

| 服务商 | 类型 | 有效期 | 说明 |
|--------|------|--------|------|
| 阿里云 | 免费 DV | 1 年 | 需每年手动续期 |
| 腾讯云 | 免费 DV | 1 年 | 需每年手动续期 |
| Cloudflare | 免费 Universal | 自动 | 自动续期，推荐使用 |
| Vercel/Netlify | 免费 | 自动 | 自动配置和续期 |

---

## 部署验证清单

部署完成后，请验证以下项目:

### 基础验证
- [ ] 网站首页能正常访问
- [ ] HTTPS 已正确配置（如启用）
- [ ] 所有页面路由正常工作
- [ ] 页面刷新后路由仍然正常（SPA 配置验证）

### 资源验证
- [ ] 所有 CSS 文件正确加载
- [ ] 所有 JavaScript 文件正确加载
- [ ] 图片资源正常显示
- [ ] 字体资源正常加载

### 功能验证
- [ ] 导航菜单正常跳转
- [ ] 表单提交功能正常
- [ ] 响应式设计正常（手机/平板/桌面）
- [ ] 浏览器兼容性正常

### 性能验证
- [ ] 使用 [PageSpeed Insights](https://pagespeed.web.dev/) 测试
- [ ] 使用 [Lighthouse](https://developer.chrome.com/docs/lighthouse/overview/) 审计
- [ ] 检查 Gzip/Brotli 压缩已启用
- [ ] 检查静态资源缓存配置正确

### 安全验证
- [ ] SSL 证书有效
- [ ] 安全头已配置（X-Frame-Options 等）
- [ ] 无敏感信息泄露
- [ ] CORS 配置正确（如有 API 调用）

---

## 故障排查

### 问题：页面空白

**可能原因**:
- JavaScript 加载失败
- 路由配置错误
- CORS 问题

**解决方案**:
1. 打开浏览器开发者工具查看控制台错误
2. 检查网络面板确认资源加载状态
3. 确认服务器配置了 SPA 路由支持

### 问题：404 错误

**可能原因**:
- 文件未正确上传
- 路由配置缺失
- Base URL 配置错误

**解决方案**:
1. 确认所有文件已上传到正确位置
2. 检查 Nginx/Apache 的 `try_files` 配置
3. 清除浏览器缓存后重试

### 问题：样式错乱

**可能原因**:
- CSS 文件加载失败
- MIME 类型配置错误
- 缓存问题

**解决方案**:
1. 检查 CSS 文件是否正确上传
2. 确认服务器配置了正确的 MIME 类型
3. 强制刷新浏览器缓存（Ctrl+F5）

### 问题：路由跳转后刷新 404

**可能原因**:
- 服务器未配置 SPA 路由支持

**解决方案**:
- Nginx: 添加 `try_files $uri $uri/ /index.html;`
- Apache: 配置 `.htaccess` 重写规则
- 静态托管：配置重定向规则

---

## 性能优化建议

### 1. 启用 Brotli 压缩（比 Gzip 更高效）

**Nginx**:
```nginx
brotli on;
brotli_comp_level 6;
brotli_types text/plain text/css application/javascript application/json;
```

**Apache**:
```apache
<IfModule mod_brotli.c>
  AddOutputFilterByType BROTLI_COMPRESS text/html text/plain text/css application/javascript
</IfModule>
```

### 2. HTTP/2 支持

**Nginx**:
```nginx
listen 443 ssl http2;
```

### 3. 预加载关键资源

在 `index.html` 中添加:
```html
<link rel="preload" href="/assets/index-xxx.css" as="style">
<link rel="preload" href="/assets/index-xxx.js" as="script">
```

### 4. 使用 CDN

将静态资源上传到 CDN 服务:
- Cloudflare (免费)
- 阿里云 OSS + CDN
- 腾讯云 COS + CDN

---

## 技术支持

如遇到部署问题:

1. **查看服务器日志**
   - Nginx: `/var/log/nginx/error.log`
   - Apache: `/var/log/apache2/error.log`

2. **浏览器开发者工具**
   - 控制台错误信息
   - 网络请求状态

3. **常用诊断命令**
   ```bash
   # 检查 Nginx 配置
   nginx -t
   
   # 检查 Apache 配置
   apache2ctl configtest
   
   # 查看服务状态
   systemctl status nginx
   systemctl status apache2
   
   # 测试 SSL 配置
   openssl s_client -connect your-domain.com:443
   ```

---

**部署包信息**:
- 生成时间: 2026-04-02
- 构建工具: Vite 5.4.21
- 框架: Vue 3.4 + TypeScript
- 包大小: 约 300KB (gzip 压缩后)
