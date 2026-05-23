def telegram_user_to_internal_user_id(telegram_user_id: int) -> str:
    return f"telegram:{telegram_user_id}"
