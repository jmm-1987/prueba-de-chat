from datetime import datetime
from typing import Optional

import requests
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length

from config import Config

db = SQLAlchemy()


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(64), nullable=False)
    message = db.Column(db.Text, nullable=False)
    direction = db.Column(db.String(16), nullable=False)  # "outgoing" o "incoming"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SendMessageForm(FlaskForm):
    chat_id = StringField(
        "Número o chatId",
        validators=[DataRequired(), Length(max=64)],
        description="Ejemplo: 34625433667@c.us",
    )
    message = TextAreaField(
        "Mensaje",
        validators=[DataRequired(), Length(max=4096)],
    )
    submit = SubmitField("Enviar mensaje")


def green_api_request(
    app: Flask, method: str, endpoint: str, data: Optional[dict] = None
) -> dict:
    instance_id = app.config.get("GREEN_INSTANCE_ID")
    token = app.config.get("GREEN_API_TOKEN")
    base_url = app.config.get("GREEN_API_URL")

    if not instance_id or not token:
        raise RuntimeError(
            "GREEN_INSTANCE_ID y GREEN_API_TOKEN deben estar configurados."
        )

    url = f"{base_url}/waInstance{instance_id}/{endpoint}/{token}"
    response = requests.request(method, url, json=data, timeout=15)
    response.raise_for_status()
    return response.json()


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.route("/health")
    def health() -> tuple[str, int]:
        return "OK", 200

    @app.route("/", methods=["GET", "POST"])
    def dashboard():
        form = SendMessageForm()
        if form.validate_on_submit():
            payload = {
                "chatId": form.chat_id.data,
                "message": form.message.data,
            }
            try:
                green_api_request(app, "POST", "sendMessage", data=payload)
                msg = ChatMessage(
                    chat_id=form.chat_id.data,
                    message=form.message.data,
                    direction="outgoing",
                )
                db.session.add(msg)
                db.session.commit()
                flash("Mensaje enviado correctamente.", "success")
                return redirect(url_for("dashboard"))
            except requests.HTTPError as exc:
                detail = ""
                if exc.response is not None:
                    try:
                        detail = exc.response.json()
                    except ValueError:
                        detail = exc.response.text
                flash(
                    f"Error al enviar el mensaje: {exc} "
                    f"{detail if detail else ''}",
                    "danger",
                )
            except RuntimeError as exc:
                flash(str(exc), "danger")

        recent_messages = (
            ChatMessage.query.order_by(ChatMessage.created_at.desc()).limit(50).all()
        )

        return render_template(
            "dashboard.html",
            form=form,
            messages=recent_messages,
        )

    @app.post("/webhook/green")
    def green_webhook():
        payload = request.json or {}
        message_data = payload.get("body", {})
        message_text = message_data.get("messageData", {}).get("textMessageData", {})
        text = message_text.get("textMessage")
        chat_id = message_data.get("senderData", {}).get("chatId")

        if text and chat_id:
            msg = ChatMessage(
                chat_id=chat_id,
                message=text,
                direction="incoming",
            )
            db.session.add(msg)
            db.session.commit()

        return "", 200

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True)

