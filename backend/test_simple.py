#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/')
def hello():
    return '''
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>🍎 Apple Bot System - Test</h1>
        <p>如果你看到这个页面，说明Flask可以正常工作</p>
        <p>时间: <span id="time"></span></p>
        <script>
            document.getElementById('time').textContent = new Date().toLocaleString();
        </script>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    return {'status': 'ok', 'message': '系统正常'}

if __name__ == '__main__':
    print("启动简化测试服务器...")
    app.run(host='0.0.0.0', port=5002, debug=True)