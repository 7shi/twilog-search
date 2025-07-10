#!/usr/bin/env python3
import asyncio
import json
import yaml
import sys
import subprocess
import argparse
import readline
from typing import Optional, Dict, Any, List
import signal
import os

class MCPWrapper:
    """MCP サーバーとの対話的な通信を提供するラッパー"""
    
    def __init__(self, command: List[str]):
        self.command = command
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self.tools_cache: Optional[Dict[str, Any]] = None
        
    def _get_next_id(self) -> int:
        """次のリクエストIDを生成"""
        self.request_id += 1
        return self.request_id
    
    async def start_server(self) -> bool:
        """MCPサーバーを起動"""
        print(f"MCPサーバーを起動中: {' '.join(self.command)}")
        
        # MCPサーバーを起動（stderrはパススルー）
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # stderrをパススルー
            text=True,
            bufsize=0
        )
        
        # 初期化メッセージを送信
        init_request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "mcp_wrap",
                    "version": "1.0.0"
                }
            }
        }
        
        await self._send_message(init_request)
        init_response = await self._receive_message()
        
        if init_response and "error" not in init_response:
            print("MCPサーバーが正常に初期化されました")
            print(yaml.dump(init_response, default_flow_style=False, allow_unicode=True).rstrip())
            
            # tools/listを取得して表示
            print("\n利用可能なツール:")
            tools_response = await self.send_request("tools/list")
            if tools_response and "result" in tools_response and "tools" in tools_response["result"]:
                self.tools_cache = tools_response["result"]  # キャッシュに保存
                tool_names = [tool["name"] for tool in tools_response["result"]["tools"]]
                print(", ".join(tool_names))
                print("\n詳細は '/help <tool_name>' で確認できます")
            else:
                print("ツール一覧の取得に失敗しました")
            
            return True
        else:
            print("MCPサーバーの初期化に失敗しました")
            if init_response:
                print(yaml.dump(init_response, default_flow_style=False, allow_unicode=True).rstrip())
            return False
    
    async def _send_message(self, message: Dict[str, Any]) -> None:
        """メッセージをサーバーに送信"""
        if not self.process or not self.process.stdin:
            raise Exception("サーバーが起動していません")
        
        json_str = json.dumps(message, ensure_ascii=False)
        self.process.stdin.write(json_str + "\n")
        self.process.stdin.flush()
    
    async def _receive_message(self) -> Optional[Dict[str, Any]]:
        """サーバーからメッセージを受信"""
        if not self.process or not self.process.stdout:
            return None
        
        line = self.process.stdout.readline()
        if line:
            return json.loads(line.strip())
        return None
    
    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """リクエストを送信してレスポンスを受信"""
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_id(),
            "method": method,
            "params": params or {}
        }
        
        try:
            await self._send_message(request)
            return await self._receive_message()
        except Exception as e:
            return {"error": f"通信エラー: {e}"}
    
    def stop_server(self) -> None:
        """MCPサーバーを停止"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
    
    def is_running(self) -> bool:
        """サーバーが動作中かチェック"""
        return self.process is not None and self.process.poll() is None

def parse_command_input(user_input: str) -> tuple[str, Optional[Dict[str, Any]]]:
    """ユーザー入力をメソッド名とパラメータに分解"""
    user_input = user_input.strip()
    
    if not user_input:
        return "", None
    
    # /helpコマンドの場合
    if user_input.startswith('/help'):
        return "/help", {"tool_name": user_input[5:].strip() if len(user_input) > 5 else ""}
    
    # JSON形式の場合
    if user_input.startswith('{'):
        try:
            data = json.loads(user_input)
            method = data.get("method", "")
            params = data.get("params", {})
            return method, params
        except json.JSONDecodeError:
            return user_input, None
    
    # スペース区切りの場合
    parts = user_input.split(' ', 1)
    method = parts[0]
    
    if len(parts) > 1:
        try:
            params = json.loads(parts[1])
        except json.JSONDecodeError:
            # JSONでない場合はそのまま文字列として扱う
            params = {"text": parts[1]}
    else:
        params = {}
    
    return method, params

async def interactive_session(wrapper: MCPWrapper) -> None:
    """対話的なセッションを開始"""
    print("\nMCPサーバーとの対話セッションを開始します")
    print("使用方法:")
    print("  method_name {\"param\": \"value\"}")
    print("  method_name text_param")
    print("  {\"method\": \"method_name\", \"params\": {\"param\": \"value\"}}")
    print("  '/quit' または '/exit' で終了")
    print()
    
    while True:
        try:
            user_input = input("> ").strip()
        except EOFError:
            print()
            break
            
        try:
            if user_input.lower() in ['/quit', '/exit', '/q']:
                print("セッションを終了します")
                break
                
            if not user_input:
                continue
            
            method, params = parse_command_input(user_input)
            
            if not method:
                print("メソッド名を指定してください")
                continue
            
            # /helpコマンドの処理
            if method == "/help":
                tool_name = params.get("tool_name", "") if params else ""
                if not tool_name:
                    # 全ツール一覧を表示
                    if wrapper.tools_cache and "tools" in wrapper.tools_cache:
                        tool_names = [tool["name"] for tool in wrapper.tools_cache["tools"]]
                        print("利用可能なツール:")
                        print(", ".join(tool_names))
                        print("\n詳細は '/help <tool_name>' で確認できます")
                    else:
                        print("ツール情報が利用できません")
                else:
                    # 特定ツールの詳細を表示
                    if wrapper.tools_cache and "tools" in wrapper.tools_cache:
                        tool_info = next((tool for tool in wrapper.tools_cache["tools"] if tool["name"] == tool_name), None)
                        if tool_info:
                            print(f"ツール: {tool_name}")
                            print(f"説明: {tool_info.get('description', 'なし')}")
                            print("パラメータ:")
                            print(yaml.dump(tool_info.get("inputSchema", {}), default_flow_style=False, allow_unicode=True).rstrip())
                        else:
                            print(f"ツール '{tool_name}' が見つかりません")
                    else:
                        print("ツール情報が利用できません")
                continue
            
            # MCPツールの呼び出し
            if wrapper.tools_cache and "tools" in wrapper.tools_cache:
                tool_names = [tool["name"] for tool in wrapper.tools_cache["tools"]]
                if method in tool_names:
                    # ツールの場合はtools/callを使用
                    response = await wrapper.send_request("tools/call", {"name": method, "arguments": params or {}})
                else:
                    # その他のメソッドは直接呼び出し
                    response = await wrapper.send_request(method, params)
            else:
                # キャッシュがない場合は直接呼び出し
                response = await wrapper.send_request(method, params)
            
            if response:
                print(yaml.dump(response, default_flow_style=False, allow_unicode=True, default_style='|').rstrip())
            else:
                print("レスポンスを受信できませんでした")
            
            print()
            
        except Exception as e:
            print(f"エラー: {e}")


async def main():
    parser = argparse.ArgumentParser(description="MCP サーバーとの対話的な通信ラッパー")
    parser.add_argument("command", nargs="+", help="MCPサーバーを起動するコマンド")
    args = parser.parse_args()
    
    wrapper = MCPWrapper(args.command)
    
    # シグナルハンドラーを設定
    def signal_handler(signum, frame):
        print("\n終了シグナルを受信しました")
        wrapper.stop_server()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # MCPサーバーを起動
        if not await wrapper.start_server():
            print("MCPサーバーの起動に失敗しました")
            sys.exit(1)
        
        # 対話的セッションを開始
        await interactive_session(wrapper)
        
    finally:
        wrapper.stop_server()

if __name__ == "__main__":
    asyncio.run(main())
