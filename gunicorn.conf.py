# gunicorn は作業ディレクトリのこのファイルを自動で読む。
# Render の GUNICORN_CMD_ARGS（--access-logfile - など）より先に読み込まれ、
# 起動コマンドを変えなくてもヘルスチェック除外が有効になる。
logger_class = "gunicorn_logger.QuietHealthLogger"
