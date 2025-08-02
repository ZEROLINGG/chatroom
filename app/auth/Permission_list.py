"""app/auth/permission_list.py"""

OTHER_PERMISSIONS = []

USER_PERMISSIONS = [

]

ADMIN_PERMISSIONS = [

]

SUPER_ADMIN_PERMISSIONS = ADMIN_PERMISSIONS + [
    "super_add_user",
    "super_get_database_info",

]

PERMISSION_GROUPS = {
    "other": OTHER_PERMISSIONS,
    "user": USER_PERMISSIONS,
    "admin": ADMIN_PERMISSIONS,
    "super_admin": SUPER_ADMIN_PERMISSIONS,
}
