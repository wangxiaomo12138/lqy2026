"""兼容入口：默认启动 Flask API（python server.py == python app.py）"""

from app import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8200, debug=False)
