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


class SyncMessagesForm(FlaskForm):
    submit = SubmitField("Sincronizar mensajes")


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
    try:
        timeout = app.config.get("GREEN_API_TIMEOUT", 15)
        if isinstance(timeout, (list, tuple)):
            timeout_value = tuple(timeout)
        else:
            timeout_value = timeout
        response = requests.request(method, url, json=data, timeout=timeout_value)
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Green-API devolvió un error: {exc}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Error de red con Green-API: {exc}") from exc

    if not response.content:
        return {}
    return response.json()


def parse_text_from_message(message_data: dict) -> Optional[str]:
    if not message_data:
        return None

    message_type = message_data.get("typeMessage")
    if message_type == "textMessage":
        return message_data.get("textMessageData", {}).get("textMessage")
    if message_type == "extendedTextMessage":
        return message_data.get("extendedTextMessageData", {}).get("textMessage")
    return None


def sync_incoming_messages(app: Flask) -> int:
    processed = 0

    while True:
        try:
            notification = green_api_request(app, "GET", "receiveNotification")
        except RuntimeError as exc:
            original = getattr(exc, "__cause__", None)
            if isinstance(original, requests.HTTPError) and original.response is not None and original.response.status_code == 404:
                break
            raise

        if not notification:
            break

        receipt_id = notification.get("receiptId")
        body = notification.get("body", {})
        chat_id = body.get("senderData", {}).get("chatId")
        message_data = body.get("messageData", {})
        text = parse_text_from_message(message_data)

        if text and chat_id:
            msg = ChatMessage(
                chat_id=chat_id,
                message=text,
                direction="incoming",
            )
            db.session.add(msg)
            db.session.commit()
            processed += 1

        if receipt_id:
            try:
                green_api_request(app, "DELETE", f"deleteNotification/{receipt_id}")
            except RuntimeError:
                pass

    return processed


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
        sync_form = SyncMessagesForm()
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
            except RuntimeError as exc:
                flash(str(exc), "danger")

        recent_messages = (
            ChatMessage.query.order_by(ChatMessage.created_at.desc()).limit(50).all()
        )

        return render_template(
            "dashboard.html",
            form=form,
            sync_form=sync_form,
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

    @app.post("/sync")
    def sync_notifications():
        form = SyncMessagesForm()
        if form.validate_on_submit():
            try:
                processed = sync_incoming_messages(app)
                if processed:
                    flash(f"{processed} mensajes sincronizados.", "success")
                else:
                    flash("No había mensajes nuevos en la cola.", "info")
            except RuntimeError as exc:
                detail = ""
                cause = getattr(exc, "__cause__", None)
                if isinstance(cause, requests.HTTPError) and cause.response is not None:
                    try:
                        detail = cause.response.json()
                    except ValueError:
                        detail = cause.response.text
                flash(f"Error al sincronizar mensajes: {exc} {detail if detail else ''}", "danger")
        else:
            flash("Solicitud inválida para sincronizar mensajes.", "danger")
        return redirect(url_for("dashboard"))

    return app


application = create_app()
app = application


if __name__ == "__main__":
    application.run(debug=True)

