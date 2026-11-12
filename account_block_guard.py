"""Deny an explicitly blocked identity before an invalid session becomes a guest."""
from flask import Response, g, jsonify, request, session

from membership import database


def guard():
    member_id = session.get('member_id')
    if not member_id:
        return
    from account_blocks import is_blocked
    with database() as conn:
        blocked = is_blocked(conn, member_id)
    if not blocked:
        return
    g.account_blocked = True
    # Keep the signed identity: clearing it would turn this request into a guest.
    if request.path.startswith('/api/'):
        response = jsonify(error='Esta cuenta está bloqueada. No dispone de acceso a electronicama.',
                           code='account_blocked')
        response.status_code = 403
    else:
        response = Response(
            '<!doctype html><html lang="es"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Acceso bloqueado · electronicama</title>'
            '<h1>Acceso bloqueado</h1><p>Esta cuenta no dispone de acceso a electronicama.</p></html>',
            status=403, content_type='text/html; charset=utf-8')
    response.headers['Cache-Control'] = 'no-store, private'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response
