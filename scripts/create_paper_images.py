#!/usr/bin/env python3
"""
为论文的9种伺服器类型准备Docker映像
特别是L3层的Flask和Express需要自定义应用
"""
import subprocess
import tempfile
from pathlib import Path
import sys

def create_flask_dockerfile():
    """建立Flask应用的Dockerfile"""
    return """FROM python:3.9-slim
WORKDIR /app
RUN pip install --no-cache-dir flask
COPY app.py /app/app.py
EXPOSE 5000
CMD ["python", "app.py"]
"""

def create_flask_app():
    """建立Flask应用程式"""
    return """from flask import Flask, request
import socket

app = Flask(__name__)

@app.route('/')
def home():
    hostname = socket.gethostname()
    return f'''<html>
<head><title>Flask Application Server</title></head>
<body>
    <h1>Flask Application Server</h1>
    <p>Python/Flask Framework</p>
    <p>Hostname: {hostname}</p>
    <p>Server Type: L3 - Application Origin</p>
</body>
</html>''', 200

@app.route('/health')
def health():
    return {'status': 'healthy', 'server': 'flask'}, 200

@app.route('/<path:path>')
def catch_all(path):
    return f'''<html>
<head><title>404 Not Found</title></head>
<body>
    <h1>404 Not Found</h1>
    <p>Flask: Path "{path}" not found</p>
    <p>Server: Flask/Python</p>
</body>
</html>''', 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
"""

def create_express_dockerfile():
    """建立Express应用的Dockerfile"""
    return """FROM node:16-slim
WORKDIR /app
COPY package.json app.js /app/
RUN npm install --production
EXPOSE 3000
CMD ["node", "app.js"]
"""

def create_express_package_json():
    """建立Express package.json"""
    return """{
  "name": "express-server",
  "version": "1.0.0",
  "description": "Express server for LLM-UnTangle research",
  "main": "app.js",
  "dependencies": {
    "express": "^4.18.0"
  },
  "engines": {
    "node": ">=16.0.0"
  }
}
"""

def create_express_app():
    """建立Express应用程式"""
    return """const express = require('express');
const os = require('os');
const app = express();

app.get('/', (req, res) => {
    const hostname = os.hostname();
    res.send(`<html>
<head><title>Express Application Server</title></head>
<body>
    <h1>Express Application Server</h1>
    <p>Node.js/Express Framework</p>
    <p>Hostname: ${hostname}</p>
    <p>Server Type: L3 - Application Origin</p>
</body>
</html>`);
});

app.get('/health', (req, res) => {
    res.json({ status: 'healthy', server: 'express' });
});

app.use((req, res) => {
    res.status(404).send(`<html>
<head><title>404 Not Found</title></head>
<body>
    <h1>404 Not Found</h1>
    <p>Express: Cannot GET ${req.path}</p>
    <p>Server: Express/Node.js</p>
</body>
</html>`);
});

const port = 3000;
app.listen(port, '0.0.0.0', () => {
    console.log(\`Express server running on port \${port}\`);
});
"""

def build_custom_images():
    """建立论文所需的自定义映像"""
    
    print("🔨 建立论文标准的L3层应用映像...")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # 建立Flask映像
        print("\n📦 建立 Flask 映像 (llm-untangle-flask:latest)...")
        flask_dir = tmpdir_path / 'flask'
        flask_dir.mkdir()
        
        (flask_dir / 'Dockerfile').write_text(create_flask_dockerfile())
        (flask_dir / 'app.py').write_text(create_flask_app())
        
        try:
            result = subprocess.run([
                'docker', 'build', '-t', 'llm-untangle-flask:latest', str(flask_dir)
            ], check=True, capture_output=True, text=True)
            print("   ✅ Flask 映像建立成功")
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Flask 映像建立失败: {e.stderr}")
            return False
        
        # 建立Express映像
        print("\n📦 建立 Express 映像 (llm-untangle-express:latest)...")
        express_dir = tmpdir_path / 'express'
        express_dir.mkdir()
        
        (express_dir / 'Dockerfile').write_text(create_express_dockerfile())
        (express_dir / 'package.json').write_text(create_express_package_json())
        (express_dir / 'app.js').write_text(create_express_app())
        
        try:
            result = subprocess.run([
                'docker', 'build', '-t', 'llm-untangle-express:latest', str(express_dir)
            ], check=True, capture_output=True, text=True)
            print("   ✅ Express 映像建立成功")
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Express 映像建立失败: {e.stderr}")
            return False
    
    print("\n" + "=" * 60)
    print("✅ 论文标准映像建立完成:")
    print("   - llm-untangle-flask:latest (Python/Flask)")
    print("   - llm-untangle-express:latest (Node.js/Express)")
    
    # 验证映像
    print("\n🔍 验证映像...")
    try:
        result = subprocess.run(['docker', 'images', 'llm-untangle-*'], 
                              capture_output=True, text=True, shell=True)
        print(result.stdout)
    except:
        pass
    
    return True

def check_docker():
    """检查Docker是否可用"""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True, check=True)
        print(f"✅ Docker 已就绪: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Docker 不可用，请确认 Docker 已安装并启动")
        return False

if __name__ == '__main__':
    print("🏗️ LLM-UnTangle 论文标准映像构建工具")
    print("=" * 60)
    
    if not check_docker():
        sys.exit(1)
    
    print("\n📋 将建立以下自定义映像:")
    print("   1. Flask 应用服务器 (L3层)")
    print("   2. Express 应用服务器 (L3层)")
    print("\n这些映像用于论文的9种服务器类型实验\n")
    
    success = build_custom_images()
    
    if success:
        print("\n🎉 所有映像建立完成！")
        print("\n下一步: python scripts/generate_paper_combinations.py")
        sys.exit(0)
    else:
        print("\n❌ 映像建立过程中出现错误")
        sys.exit(1)
