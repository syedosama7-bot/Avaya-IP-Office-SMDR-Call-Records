from flask_login import current_user

def apply_user_filter(conditions, params):
    """Add extension filter if user is not admin and has an extension."""
    if current_user.is_authenticated and current_user.role != 'admin' and current_user.extension:
        conditions.append("(caller = ? OR called_num = ?)")
        params.append(current_user.extension)
        params.append(current_user.extension)
    return conditions, params