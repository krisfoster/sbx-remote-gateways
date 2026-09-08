from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "<html><body><h1>Hello, world!</h1></body></html>"


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
