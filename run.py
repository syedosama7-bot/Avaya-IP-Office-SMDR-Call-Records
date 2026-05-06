from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host=app.config['WEB_HOST'], port=app.config['WEB_PORT'])