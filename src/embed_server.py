#!/usr/bin/env python3
import asyncio
import websockets
import json
import sys
import subprocess
import time
import argparse
import base64
from typing import Optional

HOST = "localhost"
PORT = 8765


def rpc_method(func):
    """RPC経由で呼び出し可能なメソッドをマーク"""
    func._is_rpc_method = True
    return func


class BaseEmbedServer():
    def __init__(self, model_name: str):
        self.model = None
        self.model_name = model_name
        self.init_completed = False
        self.server = None
    
    async def _start_server(self):
        """サーバーを開始"""
        try:
            self.server = await websockets.serve(self.handle_client, HOST, PORT)
            await self.server.serve_forever()
        except asyncio.CancelledError:
            pass
    
    async def _stop_server(self):
        """サーバーを停止"""
        self.server.close()
        await self.server.wait_closed()
    
    async def report_progress(self, message):
        """フロント側に進捗報告"""
        try:
            websocket = await websockets.connect(f"ws://{HOST}:{PORT}")
            await send_json(websocket, {"type": "progress", "message": message})
            await websocket.close()
        except Exception:
            # フロント側が利用できない場合は標準エラー出力に出力
            print(message, file=sys.stderr)
    
    async def notify_frontend_completion(self):
        """フロント側WebSocketサーバーに初期化完了を通知"""
        try:
            websocket = await websockets.connect(f"ws://{HOST}:{PORT}")
            await send_json(websocket, {"type": "init_completed"})
            
            # フロント側からの返事を待つ
            _ = await websocket.recv()
            await websocket.close()
            
            await asyncio.sleep(3)
            
        except Exception:
            pass
    
    async def notify_frontend_error(self, error_message: str):
        """フロント側WebSocketサーバーに初期化エラーを通知"""
        try:
            websocket = await websockets.connect(f"ws://{HOST}:{PORT}")
            await send_json(websocket, {"type": "init_error", "error": error_message})
            await websocket.close()
        except Exception:
            pass

    async def handle_client(self, websocket):
        try:
            async for message in websocket:
                data = json.loads(message)
                
                method = data.get("method")
                params = data.get("params", {})
                request_id = data.get("id")
                
                # JSON-RPCフォーマットを確認
                if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
                    # 旧形式をサポートしない
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32600,
                            "message": "Invalid Request: missing jsonrpc field"
                        }
                    }
                    await send_json(websocket, error_response)
                    continue
                
                # メソッド名でディスパッチ
                try:
                    method_handler = getattr(self, method, None)
                    if getattr(method_handler, '_is_rpc_method', False):
                        result = await method_handler(**params)
                        
                        # Streaming Extensions対応（dictかつstreamingフィールドのみを含む場合のみ）
                        if isinstance(result, dict) and len(result) == 1 and "streaming" in result:
                            chunks = result["streaming"]
                            last = len(chunks) - 1
                            for i, chunk_data in enumerate(chunks):
                                response = {
                                    "jsonrpc": "2.0",
                                    "id": request_id,
                                    "result": chunk_data,
                                    "more": i < last  # 続きがあるかどうか
                                }
                                await send_json(websocket, response)
                        else:
                            # 通常のレスポンス
                            response = {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "result": result
                            }
                            await send_json(websocket, response)
                        
                        # stop_serverの場合は接続を終了
                        if method == "stop_server":
                            await self._stop_server()
                            break
                    else:
                        # 未知のメソッド
                        error_response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32601,
                                "message": f"Method not found: {method}"
                            }
                        }
                        await send_json(websocket, error_response)
                except Exception as e:
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32603,
                            "message": str(e)
                        }
                    }
                    await send_json(websocket, error_response)
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass


class EmbedServer(BaseEmbedServer):
    """基本的な埋め込みサーバー実装"""
    
    async def start_server(self):
        try:
            # 非同期で初期化処理を実行
            await self.init_model()
        
        except Exception as e:
            await self.report_progress(f"初期化エラー: {e}")
            await self.notify_frontend_error(str(e))
            return
        
        # 初期化完了後、フロント側に通知
        await self.notify_frontend_completion()
        
        # サーバーを開始
        await self._start_server()
    
    async def _init_model(self):
        """初期化処理"""
        await self.report_progress("torch読み込み開始...")
        start_time = time.monotonic()
        import torch
        torch_time = time.monotonic() - start_time
        await self.report_progress(f"torch読み込み完了 ({torch_time:.2f}秒)")
        
        await self.report_progress("transformers読み込み開始...")
        start_time = time.monotonic()
        import transformers
        transformers_time = time.monotonic() - start_time
        await self.report_progress(f"transformers読み込み完了 ({transformers_time:.2f}秒)")
        
        await self.report_progress("sentence_transformers読み込み開始...")
        start_time = time.monotonic()
        from sentence_transformers import SentenceTransformer
        sentence_transformers_time = time.monotonic() - start_time
        await self.report_progress(f"sentence_transformers読み込み完了 ({sentence_transformers_time:.2f}秒)")
        
        await self.report_progress(f"{self.model_name}モデル初期化開始...")
        start_time = time.monotonic()
        self.model = SentenceTransformer(self.model_name)
        model_time = time.monotonic() - start_time
        await self.report_progress(f"{self.model_name}モデル初期化完了 ({model_time:.2f}秒)")
    
    async def init_model(self):
        """初期化処理の時間計測"""
        if not self.model_name:
            raise ValueError("モデルが指定されていません")
        
        total_start = time.monotonic()
        
        # サーバー種類を進捗として報告（クラス名）
        await self.report_progress(f"サーバー種類: {self.__class__.__name__}")
        
        # 初期化処理
        await self._init_model()
        
        total_time = time.monotonic() - total_start
        await self.report_progress(f"全初期化完了 (合計: {total_time:.2f}秒)")
        
        self.init_completed = True
    
    @rpc_method
    async def get_status(self):
        """ステータスを取得"""
        return {
            "status": "running", 
            "ready": self.init_completed,
            "server_type": self.__class__.__name__,
            "model": self.model_name
        }
    
    @rpc_method
    async def check_init(self):
        """初期化状況を確認"""
        if self.init_completed:
            return {"status": "init_completed"}
        else:
            return {"status": "init_in_progress"}
    
    @rpc_method
    async def stop_server(self):
        """サーバーを停止"""
        return {"status": "stopping"}
    
    def _embed_text(self, query: str):
        """クエリをベクトル化"""
        if self.model is None:
            raise RuntimeError("モデルが初期化されていません")
        
        # SentenceTransformerでベクトル化
        return self.model.encode([query], normalize_embeddings=True, convert_to_tensor=True)
    
    def _encode_vector_to_safetensors(self, vector):
        """ベクトルをsafetensors形式でbase64エンコード"""
        import safetensors.torch
        
        # tensorをCPUに移動（必要に応じて）
        if hasattr(vector, 'cpu'):
            vector = vector.cpu()
        
        # safetensorsとしてバイト列を生成
        tensors = {"vector": vector}
        data = safetensors.torch.save(tensors)
        
        # base64エンコード
        encoded_data = base64.b64encode(data).decode('utf-8')
        return encoded_data
    
    @rpc_method
    async def embed_text(self, text: str):
        """クエリをベクトル化"""
        if not self.init_completed:
            raise RuntimeError("モデルがまだ初期化されていません")
        
        if not text:
            raise ValueError("text is required")
        
        vector = self._embed_text(text)
        # safetensorsとしてエンコード
        vector_data = self._encode_vector_to_safetensors(vector)
        
        return {"vector": vector_data}


async def send_json(websocket, request: dict):
    """WebSocketを通じてJSON-RPCリクエストを送信"""
    await websocket.send(json.dumps(request, ensure_ascii=False))

async def check_server_status() -> Optional[dict]:
    try:
        websocket = await asyncio.wait_for(
            websockets.connect(f"ws://{HOST}:{PORT}"),
            timeout=5
        )
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "get_status",
            "params": {}
        }
        await send_json(websocket, request)
        response = await websocket.recv()
        await websocket.close()
        
        response_data = json.loads(response)
        if response_data.get("jsonrpc") == "2.0" and "result" in response_data:
            return response_data["result"]
        return None
    except Exception:
        return None

async def stop_server():
    try:
        websocket = await asyncio.wait_for(
            websockets.connect(f"ws://{HOST}:{PORT}"),
            timeout=5
        )
    except Exception:
        print("サーバーは起動していません")
        return
        
    try:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "stop_server",
            "params": {}
        }
        await send_json(websocket, request)
        response = await websocket.recv()
        await websocket.close()
        
        response_data = json.loads(response)
        if response_data.get("jsonrpc") == "2.0":
            if "result" in response_data:
                print(f"停止指示を送信: {response_data['result']}")
            elif "error" in response_data:
                print(f"停止指示エラー: {response_data['error']['message']}")
        else:
            print(f"停止指示を送信: {response}")
    except Exception as e:
        print(f"停止指示の送信に失敗: {e}")


class FrontendServer:
    def __init__(self):
        self.init_complete_event = asyncio.Event()
        self.init_error_event = asyncio.Event()
        self.error_message = None
        
    async def notification_handler(self, websocket):
        """フロント側で初期化完了通知を受信"""
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get("type") == "progress":
                    print(f"進捗: {data.get('message')}")
                elif data.get("type") == "init_completed":
                    print("デーモンからの初期化完了通知を受信しました")
                    # 返事を送信
                    await send_json(websocket, {"type": "ack"})
                    # イベントをセット
                    self.init_complete_event.set()
                    return
                elif data.get("type") == "init_error":
                    error_msg = data.get("error", "不明なエラー")
                    print(f"デーモンからの初期化エラー通知を受信: {error_msg}")
                    self.error_message = error_msg
                    # エラーイベントをセット
                    self.init_error_event.set()
                    return
        except Exception as e:
            print(f"通知受信エラー: {e}")
    
    async def wait_for_init_complete(self):
        """初期化完了または失敗を待機"""
        done, pending = await asyncio.wait([
            asyncio.create_task(self.init_complete_event.wait()),
            asyncio.create_task(self.init_error_event.wait())
        ], return_when=asyncio.FIRST_COMPLETED)
        
        # 残りのタスクをキャンセル
        for task in pending:
            task.cancel()
        
        # エラーが発生した場合は例外を発生
        if self.init_error_event.is_set():
            raise RuntimeError(f"初期化エラー: {self.error_message}")

async def start_daemon(daemon_args: list, **kwargs):
    try:
        # フロント側WebSocketサーバーでポート重複チェック
        print("デーモンの存在確認中...")
        frontend = FrontendServer()
        frontend_server = await websockets.serve(
            frontend.notification_handler, HOST, PORT
        )
        print("デーモンは起動していません。新規起動します...")
        
    except OSError as e:
        if "Address already in use" in str(e):
            print("デーモンは既に起動しています")
            
            # 初期化状況を確認
            status = await check_server_status()
            if status:
                print(f"デーモン状態: {status}")
            else:
                print("デーモンに接続できませんでした")
        else:
            raise
        
    # デーモンプロセス起動
    proc = subprocess.Popen(
        daemon_args,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL, start_new_session=True
    )
    print("デーモンプロセスを起動しました")
    
    # 初期化完了通知を待機
    print("初期化完了通知を待機中...")
    
    # サーバーを起動し、同時に初期化完了を待機
    server_task = asyncio.create_task(frontend_server.serve_forever())
    init_task = asyncio.create_task(frontend.wait_for_init_complete())
    
    # 初期化完了まで待機（エラーの場合は例外が発生）
    try:
        await init_task
        init_completed = True
    except RuntimeError as e:
        print(f"初期化に失敗しました: {e}")
        init_completed = False
    
    # サーバーを停止
    frontend_server.close()
    await frontend_server.wait_closed()
    try:
        server_task.cancel()
        await server_task
    except asyncio.CancelledError:
        pass
    
    print("フロント側サーバーを停止しました")
    
    # エラーの場合は終了
    if not init_completed:
        return
    
    # 5秒待機後、デーモンサーバーへの接続確認
    print("5秒待機後、デーモンサーバーへの接続を確認します...")
    await asyncio.sleep(5)
    
    status = await check_server_status()
    if status:
        print(f"デーモンサーバーの起動を確認しました: {status}")
    else:
        print("デーモンサーバーへの接続に失敗しました")

async def main():
    parser = argparse.ArgumentParser(description="Embed Server Daemon Management")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # start command
    start_parser = subparsers.add_parser('start', help='Start the daemon server')
    start_parser.add_argument('-m', '--model', required=True, 
                             help='使用するモデル名（必須）')
    
    # stop command
    subparsers.add_parser('stop', help='Stop the daemon server')
    
    # status command (default)
    subparsers.add_parser('status', help='Check daemon server status')
    
    # hidden _daemon command for internal use
    daemon_parser = subparsers.add_parser('_daemon', help=argparse.SUPPRESS)
    daemon_parser.add_argument('-m', '--model', required=True, 
                              help='使用するモデル名（必須）')
    
    args = parser.parse_args()
    
    if args.command == "_daemon":
        # デーモンモード
        server = EmbedServer(args.model)
        await server.start_server()
    elif args.command == "start":
        # 起動処理
        print("サーバーを起動します...")
        # デーモン起動引数を作成
        daemon_args = [
            sys.executable, __file__, "_daemon",
            "-m", args.model
        ]
        await start_daemon(daemon_args)
    elif args.command == "stop":
        # 停止処理
        await stop_server()
    else:
        # 引数なしまたはstatus: ステータス確認
        status = await check_server_status()
        if status:
            print(f"サーバーステータス: {status}")
        else:
            print("サーバーは起動していません")

if __name__ == "__main__":
    asyncio.run(main())
