import requests
import re
import json
from urllib.parse import urljoin, quote, unquote, parse_qs, urlparse
import base64
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
import time
from bs4 import BeautifulSoup
import os
import subprocess
import sys
import ddddocr


class FZMTRLogin:
    def __init__(self, use_env_proxy=False):
        self.session = requests.Session()
        self.session.trust_env = bool(use_env_proxy)
        if not use_env_proxy:
            self.session.proxies = {}

        self.base_url = "http://sso.fzmtr.com/sso"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,zh-TW;q=0.8,en-US;q=0.7,en;q=0.6,zh-HK;q=0.5',
        }

    def get_csrf_token_and_public_key(self):
        login_url = urljoin(self.base_url, "/sso/login")
        response = self.session.get(login_url, headers=self.headers)

        if response.status_code != 200:
            raise Exception(f"获取登录页面失败: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')

        csrf_meta = soup.find('meta', {'name': 'csrf'})
        if csrf_meta and csrf_meta.get('content'):
            csrf_token = csrf_meta['content']
        else:
            csrf_input = soup.find('input', {'name': 'csrf_token'})
            csrf_token = csrf_input['value'] if csrf_input else None

        if not csrf_token:
            raise Exception("未找到csrf_token")

        public_key = None
        for script in soup.find_all('script'):
            if script.string and 'Global.ssoPublicKey' in script.string:
                match = re.search(r"Global\.ssoPublicKey\s*=\s*'([^']+)'", str(script.string))
                if match:
                    public_key = match.group(1).strip()
                    public_key = public_key.replace('\\n', '\n')
                    public_key = public_key.strip().strip('"').strip("'")

                    if 'BEGIN PUBLIC KEY' not in public_key:
                        b64 = re.sub(r"\s+", '', public_key)
                        b64 = b64.replace('\\n', '')
                        pad = (-len(b64)) % 4
                        if pad:
                            b64 += '=' * pad
                        lines = [b64[i:i+64] for i in range(0, len(b64), 64)]
                        public_key = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----"
                    break

        if not public_key:
            raise Exception("未找到RSA公钥")

        return_url_input = soup.find('input', {'id': 'return_url'})
        return_url = return_url_input['value'] if return_url_input else ''

        client_id_input = soup.find('input', {'id': 'client_id'})
        client_id = client_id_input['value'] if client_id_input else ''

        domain_input = soup.find('input', {'id': 'domain'})
        domain = domain_input['value'] if domain_input else ''

        return csrf_token, public_key, return_url, client_id, domain

    def rsa_encrypt(self, text, public_key_str):
        pem_key = None
        try:
            pk = public_key_str.strip()
            if 'BEGIN PUBLIC KEY' in pk:
                pem_key = pk
            else:
                candidates = [pk, pk.replace('\\n', '')]
                for cand in candidates:
                    b64 = re.sub(r"[^A-Za-z0-9+/=]", '', cand)
                    pad = (-len(b64)) % 4
                    if pad:
                        b64 += '=' * pad
                    lines = [b64[i:i+64] for i in range(0, len(b64), 64)]
                    attempt_pem = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----"
                    try:
                        RSA.importKey(attempt_pem)
                        pem_key = attempt_pem
                        break
                    except Exception:
                        pem_key = attempt_pem

            if not pem_key:
                raise Exception("无法从页面提取有效的公钥")

            rsa_key = RSA.importKey(pem_key)
            cipher = PKCS1_v1_5.new(rsa_key)
            encrypted = cipher.encrypt(text.encode('utf-8'))
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            raise Exception(f"RSA加密失败: {e}")

    def get_validate_code_image(self, csrf_token, max_retries=3):
        ocr = ddddocr.DdddOcr(show_ad=False)

        for attempt in range(max_retries):
            timestamp = int(time.time() * 1000)
            validate_code_url = f"{self.base_url}/validatecode/image"
            params = {'req_id': csrf_token, 'time': timestamp}

            response = self.session.get(validate_code_url, params=params, headers=self.headers)

            if response.status_code != 200:
                raise Exception(f"获取验证码失败: {response.status_code}")

            base_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_dir, 'validate_code.png')
            with open(file_path, 'wb') as f:
                f.write(response.content)

            with open(file_path, 'rb') as f:
                validate_code = ocr.classification(f.read())

            validate_code = validate_code.strip()

            if validate_code and len(validate_code) >= 4:
                print(f"第 {attempt + 1} 次识别成功: {validate_code}")
                return validate_code

            print(f"第 {attempt + 1} 次识别失败: '{validate_code}', 重试中...")

        raise Exception(f"验证码识别失败，已重试 {max_retries} 次")

    def login(self, username, password):
        csrf_token, public_key, return_url, client_id, domain = self.get_csrf_token_and_public_key()

        validate_code = self.get_validate_code_image(csrf_token)

        encrypted_username = self.rsa_encrypt(username, public_key)
        encrypted_password = self.rsa_encrypt(password, public_key)

        login_data = {
            'csrf_token': csrf_token,
            'return_url': return_url,
            'client_id': client_id,
            'username': encrypted_username,
            'username_text': username,
            'domain': domain,
            'encrypt_type': 'rsa',
            'encrypt_type_username': 'rsa',
            'password_text': '',
            'password': encrypted_password,
            'validateCode': validate_code
        }

        login_url = urljoin(self.base_url, "/sso/login")
        response = self.session.post(login_url, data=login_data, headers=self.headers)

        if response.status_code == 200:
            success_indicators = ["登录成功", "登陆成功", "我的首页", "已登录", "欢迎", "redirect"]
            if any(ind in response.text for ind in success_indicators):
                print("登录成功!")
                cookies = self.session.cookies.get_dict()
                return {'success': True, 'cookies': cookies}
            else:
                print("登录失败，未知错误")
                return {'success': False, 'error': '登录失败'}
        else:
            print(f"登录请求失败，状态码: {response.status_code}")
            return {'success': False, 'error': f'HTTP {response.status_code}'}

    def oauth2_authorize(self, auth_token, tk='e470d4eb1406b766e15324a451844ab0', authurl='oauth2'):
        redirect_uri = quote(f'http://newoa.fzmtr.com/build/intauthclient/verify/index.html?tk={tk}&authurl={authurl}')
        params = {
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'client_id': 'clientId9'
        }

        url = urljoin(self.base_url, '/sso/oauth2/authorize')
        headers = dict(self.headers)
        headers['Cookie'] = f'auth_token_fzmtr.linksso_test_cookie={auth_token}'

        response = self.session.get(url, params=params, headers=headers, allow_redirects=False)

        location = response.headers.get('Location')
        if location:
            return location
        else:
            print(f"OAuth2 authorize 未返回 Location header，状态码: {response.status_code}")
            return None


def main():
    login_client = FZMTRLogin()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_path = os.path.join(base_dir, 'eteamsid_cache.json')

    # ============================================
    # 第一步：尝试从本地缓存读取 ETEAMSID
    # ============================================
    eteamsid = None
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
            eteamsid = cache.get('eteamsid')

    # ============================================
    # 第二步：验证缓存的 ETEAMSID 是否有效
    # ============================================
    if eteamsid:
        print(f"使用缓存的ETEAMSID: {eteamsid}")
        test_resp = login_client.session.post(
            'http://newoa.fzmtr.com/api/workflow/list/data/getPortalListData',
            headers={'Content-Type': 'application/json', 'Cookie': f'ETEAMSID={eteamsid}'},
            json={
                "compId": "fcb582ecc2744ac985a8f51d93cb7d6a",
                "pageId": "1162382583372750853",
                "appId": "1162382527454289920",
                "pageNo": "1",
                "pageSize": "1",
                "filterParam": {"type": "701", "checks": ""},
                "conditionComId": "",
                "wea_link_keep_loginType": "intunifyauth",
                "cusMenuId": "1165734139413716993",
                "urlPageTitle": "6aaW6aG1",
                "filter": [],
                "pageFilter": {"filterIsNull": True, "esbFilter": []},
                "fileds": ["requestname", "creatername", "createdatetime"],
                "params": {"continueDimension": "todo", "src": "ebuild"}
            }
        )
        if test_resp.status_code == 200 and test_resp.json().get('code') == 200:
            print("缓存的ETEAMSID有效，跳过登录")
        else:
            print("缓存的ETEAMSID已失效，需要重新登录")
            eteamsid = None

    # ============================================
    # 第三步：缓存无效时，重新登录获取 ETEAMSID
    # ============================================
    if not eteamsid:
        # 从配置文件读取账号密码
        config_path = os.path.join(base_dir, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        username = config.get('username', '')
        password = config.get('password', '')

        # SSO 登录（需输入验证码）
        result = login_client.login(username, password)

        if result.get('success'):
            cookies = result.get('cookies', {})
            auth_token = cookies.get('auth_token_fzmtr.linksso_test_cookie')

            if auth_token:
                # 调用 OAuth2 接口获取授权，重定向到 newoa
                location = login_client.oauth2_authorize(auth_token=auth_token)
                if location:
                    decoded_url = unquote(location)
                    last_qmark = decoded_url.rfind('?')
                    if last_qmark != -1:
                        decoded_url = decoded_url[:last_qmark] + '&' + decoded_url[last_qmark+1:]

                    parsed = urlparse(decoded_url)
                    params = parse_qs(parsed.query)
                    tk = params.get('tk', [''])[0]
                    authurl = params.get('authurl', [''])[0]
                    code = params.get('code', [''])[0]

                    # 构建最终 URL，访问后会在 Cookie 中获得 ETEAMSID
                    final_url = f"http://newoa.fzmtr.com/papi/bs/iaauthlogin/login/oauth2?tk={tk}&authurl={authurl}&code={code}&oaUrl=http%3A%2F%2Fnewoa.fzmtr.com"
                    print(f"\n通过以下链接获取ETEAMSID:\n{final_url}")

                    eteamsid_resp = login_client.session.get(final_url, headers=login_client.headers, allow_redirects=True)
                    for name, value in eteamsid_resp.cookies.items():
                        if name == 'ETEAMSID':
                            eteamsid = value
                            print(f"\nETEAMSID: {value}")
                            # 缓存到本地文件，下次启动可直接使用
                            with open(cache_path, 'w', encoding='utf-8') as f:
                                json.dump({'eteamsid': eteamsid}, f)
                            break

    # ============================================
    # 第四步：使用 ETEAMSID 获取待阅列表并处理
    # ============================================
    if eteamsid:
        api_url = 'http://newoa.fzmtr.com/api/workflow/list/data/getPortalListData'
        api_headers = {
            'Content-Type': 'application/json',
            'Cookie': f'ETEAMSID={eteamsid}',
            'User-Agent': login_client.headers.get('User-Agent'),
        }
        api_payload = {
            "compId": "fcb582ecc2744ac985a8f51d93cb7d6a",
            "pageId": "1162382583372750853",
            "appId": "1162382527454289920",
            "pageNo": "1",
            "pageSize": "20",
            "filterParam": {"type": "701", "checks": ""},
            "conditionComId": "",
            "wea_link_keep_loginType": "intunifyauth",
            "cusMenuId": "1165734139413716993",
            "urlPageTitle": "6aaW6aG1",
            "filter": [],
            "pageFilter": {"filterIsNull": True, "esbFilter": []},
            "fileds": ["requestname", "creatername", "createdatetime"],
            "params": {"continueDimension": "todo", "src": "ebuild"}
        }
        api_resp = login_client.session.post(api_url, headers=api_headers, json=api_payload)
        api_data = api_resp.json()

        # ============================================
        # 第五步：按 isremark 类型分类待阅数据
        #    - isremark=20：手动已阅，需要调用 /flow/annotation 接口
        #    - isremark=60：自动已阅，需要调用 /flowPage/updateReqInfo 接口
        # ============================================
        manual_read = []
        auto_read = []
        for item in api_data.get('data', {}).get('data', []):
            isremark = item.get('isremark')
            if isremark == 20:
                manual_read.append(item)
            elif isremark == 60:
                auto_read.append(item)

        # 处理手动已阅（isremark=20）
        print(f"\n手动已阅类 (isremark=20): {len(manual_read)}条")
        for item in manual_read:
            req_data = {
                "requestId": item.get('requestid'),
                "userCurrentNodeId": item.get('nodeid'),
                "isRemark": 20,
                "src": "instruction"
            }
            resp = login_client.session.post(
                'http://newoa.fzmtr.com/api/workflow/core/flow/annotation',
                headers={'Content-Type': 'application/json', 'Cookie': f'ETEAMSID={eteamsid}'},
                json=req_data
            )
            print(f"requestid: {item.get('requestid')}, nodeid: {item.get('nodeid')}, isremark: {item.get('isremark')}, response: {resp.text[:100]}")

        # 处理自动已阅（isremark=60）
        print(f"\n自动已阅类 (isremark=60): {len(auto_read)}条")
        for item in auto_read:
            req_data = {"requestId": item.get('requestid')}
            resp = login_client.session.post(
                'http://newoa.fzmtr.com/api/workflow/core/flowPage/updateReqInfo',
                headers={'Content-Type': 'application/json', 'Cookie': f'ETEAMSID={eteamsid}'},
                json=req_data
            )
            print(f"requestid: {item.get('requestid')}, nodeid: {item.get('nodeid')}, isremark: {item.get('isremark')}, response: {resp.text[:100]}")


if __name__ == "__main__":
    main()
