#!/usr/bin/env python3
import asyncio
import websockets
import json
import yaml
import argparse
import base64
from typing import Optional, Dict, List, Any

HOST = "localhost"
PORT = 8765


def rpc_method(func):
    """RPC経由で呼び出し可能なメソッドをマーク"""
    func._is_rpc_method = True
    return func


# グローバル連番カウンター
_request_id_counter = 0

def _get_next_request_id() -> int:
    """次のリクエストIDを取得"""
    global _request_id_counter
    _request_id_counter += 1
    return _request_id_counter


class BaseEmbedClient():
    """ベースクライアントクラス - 継承して拡張可能"""
    
    def __init__(self, host: str = HOST, port: int = PORT, timeout: int = 10):
        self.host = host
        self.port = port
        self.timeout = timeout
    
    async def _send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any] | List[Dict]:
        """WebSocketリクエストの基本送信処理（JSON-RPC 2.0形式）"""
        websocket = None
        try:
            websocket = await asyncio.wait_for(
                websockets.connect(f"ws://{self.host}:{self.port}"),
                timeout=self.timeout
            )
            
            id = _get_next_request_id()
            
            # JSON-RPC 2.0リクエスト形式
            request = {
                "jsonrpc": "2.0",
                "id": id,
                "method": method,
                "params": params or {}
            }
            
            await websocket.send(json.dumps(request, ensure_ascii=False))
            
            results = []
            while True:
                response = await websocket.recv()
                response_data = json.loads(response)
                
                # JSON-RPCレスポンスの処理
                if response_data.get("jsonrpc") != "2.0":
                    return {"error": "サーバーがJSON-RPC 2.0形式に対応していません"}
                if response_data.get("id") != id:
                    return {"error": "不正なリクエストIDのレスポンスを受信しました"}
                if "error" in response_data:
                    return {"error": response_data["error"]["message"]}
                if "result" not in response_data:
                    return {"error": "Invalid JSON-RPC response"}
                
                # 分割送信かを確認
                more = response_data.get("more")
                if more is None:
                    if results:
                        return {"error": "サーバーからのレスポンスに'more'フィールドがありません"}
                    else:
                        return response_data["result"]

                # 分割送信された結果を追加
                results.append(response_data["result"])
                
                # 最後のチャンクならループを抜ける
                if not more:
                    break

            # 分割送信の結果を返す
            return results
            
        except asyncio.TimeoutError:
            return {"error": "サーバーへの接続がタイムアウトしました"}
        except ConnectionRefusedError:
            return {"error": "サーバーが起動していません"}
        except Exception as e:
            return {"error": f"通信エラー: {e}"}
            
        finally:
            if websocket:
                await websocket.close()
    
    def is_success(self, response: Dict[str, Any]) -> bool:
        """レスポンスが成功かどうかを判定"""
        return "error" not in response


class EmbedClient(BaseEmbedClient):
    """基本的な埋め込みクライアント実装"""
    
    @rpc_method
    async def get_status(self) -> Dict[str, Any]:
        """サーバーステータスを取得"""
        return await self._send_request("get_status")
    
    @rpc_method
    async def check_init(self) -> Dict[str, Any]:
        """初期化状況を確認"""
        return await self._send_request("check_init")
    
    @rpc_method
    async def stop_server(self) -> Dict[str, Any]:
        """サーバーを停止"""
        return await self._send_request("stop_server")
    
    def _extract_vector_data(self, response: Dict[str, Any]) -> Optional[str]:
        """ベクトルデータを抽出"""
        if self.is_success(response) and "vector" in response:
            return response["vector"]
        return None
    
    def _decode_vector_size(self, vector_data: str) -> Optional[int]:
        """Base64ベクトルデータのサイズを取得"""
        try:
            decoded_data = base64.b64decode(vector_data)
            return len(decoded_data)
        except Exception:
            return None
    
    @rpc_method
    async def embed_text(self, text: str) -> Dict[str, Any]:
        """クエリをベクトル化"""
        return await self._send_request("embed_text", {"text": text})
    
    async def embed_text_with_details(self, query: str) -> None:
        """詳細情報付きでベクトル化を実行し結果を表示"""
        print(f"クエリ: {query}")
        print("サーバーに接続中...")
        
        result = await self.embed_text(query)
        
        if not self.is_success(result):
            print(f"エラー: {result['error']}")
            return
        
        vector_data = self._extract_vector_data(result)
        if vector_data:
            decoded_size = self._decode_vector_size(vector_data)
            print(f"ベクトル化成功!")
            print(f"Base64データ（先頭20文字）: {vector_data[:20]}")
            print(f"Base64データ長: {len(vector_data)}文字")
            print(f"デコード後サイズ: {decoded_size}バイト" if decoded_size else "デコード後サイズ: デコードエラー")
        else:
            print(f"予期しないレスポンス: {result}")


class EmbedCommand:
    """EmbedClientのコマンドライン操作を管理するクラス"""
    
    def __init__(self, client: EmbedClient = None):
        self.client = client or EmbedClient()
    
    def create_parser(self) -> argparse.ArgumentParser:
        """argparseのparserを作成"""
        parser = argparse.ArgumentParser(description="Embed Server Test Client")
        subparsers = parser.add_subparsers(dest='command', help='利用可能なコマンド')
        
        # get_status command
        subparsers.add_parser('get_status', help='サーバーステータスを確認')
        
        # check_init command  
        subparsers.add_parser('check_init', help='初期化状態を確認')
        
        # stop_server command
        subparsers.add_parser('stop_server', help='サーバーを停止')
        
        # embed_text command
        embed_text_parser = subparsers.add_parser('embed_text', help='テキストをベクトル化')
        embed_text_parser.add_argument('text', help='ベクトル化するテキスト')
        
        return parser
    
    @rpc_method
    async def embed_text(self, args) -> None:
        """embed_textコマンドの処理"""
        await self.client.embed_text_with_details(args.text)

    async def execute(self, args_list: list = None) -> None:
        """コマンドを実行"""
        parser = self.create_parser()
        args = parser.parse_args(args_list)
        
        if not args.command:
            parser.print_help()
            return
        
        # サブコマンド名と同名のメソッドを呼び出し
        try:
            command_method = getattr(self, args.command, None)
            if getattr(command_method, '_is_rpc_method', False):
                await command_method(args)
            else:
                # EmbedCommandにメソッドが見つからない場合、EmbedClientを呼び出してYAML表示
                client_method = getattr(self.client, args.command, None)
                if getattr(client_method, '_is_rpc_method', False):
                    result = await client_method()
                    print(yaml.dump(result, default_flow_style=False, allow_unicode=True).rstrip())
                else:
                    print(f"不明なコマンド: {args.command}")
        except Exception as e:
            print(f"エラー: {e}")


async def main():
    """CLIクライアント使用例"""
    command = EmbedCommand()
    await command.execute()


if __name__ == "__main__":
    asyncio.run(main())
