from datetime import datetime, timedelta
from urllib.parse import quote_plus

from flask_restful import Resource
from flask import redirect, request

from lib.config import REDIRECT_URI, client_id, domain_name as DOMAIN
from lib.status_codes import StatusCodes
from lib.auth import JWT, flask_authenticated as authenticated

from src.util import CustomResource, reqparams
from src.discord_requests import identify_request, token_exchange_request

SAFE_REDIRECT_URI = quote_plus(REDIRECT_URI)


class Login(CustomResource):
    def get(self):
        response = redirect(f'https://discordapp.com/api/oauth2/authorize?client_id={client_id}&redirect_uri='
                            f'{SAFE_REDIRECT_URI}&response_type=code&scope=identify%20guilds')
        # TODO check if requested return url is owned by us
        # if not any(re.match(pattern, url) for pattern in (
        #         r'https:\/\/[-A-Za-z0-9]{24}--architus\.netlify\.com\/app',
        #         r'https:\/\/deploy-preview-[0-9]+--architus\.netlify\.com\/app',
        #         r'https:\/\/develop\.archit\.us\/app',
        #         r'https:\/\/archit\.us\/app',
        #         r'http:\/\/localhost:3000\/app')):
        #     url = CALLBACK_URL

        # TODO default destination if return is not included
        response.set_cookie(
            'next',
            request.args.get('return') or f'https://{DOMAIN}/app',
            domain=f'api.{DOMAIN}',
            secure=True, httponly=True
        )
        return response


class RefreshToken(CustomResource):
    pass


class TokenExchange(Resource):
    @reqparams(code=str)
    def post(self, code: str):
        ex_data, status_code = token_exchange_request(code)

        if status_code == StatusCodes.OK_200:
            discord_token = ex_data['access_token']
            id_data, status_code = identify_request(discord_token)
            if status_code == StatusCodes.OK_200:
                now = datetime.now()
                expires_in = ex_data['expires_in']
                refresh_in = timedelta(seconds=expires_in) / 2
                jwt = JWT({
                    'access_token': discord_token,
                    'refresh_token': ex_data['refresh_token'],
                    'expires_in': expires_in,
                    'issued_at': now.isoformat(),
                    'id': id_data['id'],
                    'permissions': 274,
                })
                data = {
                    # 'token': jwt.get_token()
                    'user': id_data,
                    'access': {
                        'issuedAt': now.isoformat(),
                        'expiresIn': expires_in,
                        'refreshIn': int(refresh_in.total_seconds()),
                    }
                }

                cookie = {
                    'Set-Cookie':
                        f'token={jwt.get_token()}; Max-Age={expires_in * 2}; Domain=.{DOMAIN}; Secure; HttpOnly;'
                }
                return data, StatusCodes.OK_200, cookie

        return ex_data, status_code


class Identify(Resource):
    @authenticated
    def get(self, jwt: JWT):
        '''Forward identify request to discord and return response'''
        return identify_request(jwt.access_token)
