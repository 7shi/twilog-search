#!/usr/bin/env python3
"""
Twilog検索サーバー用クライアント
"""
import asyncio
import argparse
from typing import Dict, Optional
from urllib.parse import urlparse
from embed_client import EmbedClient, EmbedCommand


class TwilogClient(EmbedClient):
    """Twilog検索サーバーへのクライアント - EmbedClientを継承"""
    
    def __init__(self, websocket_url: str = "ws://localhost:8765"):
        """
        初期化
        
        Args:
            websocket_url: WebSocketサーバーのURL
        """
        self.websocket_url = websocket_url
        parsed_url = urlparse(websocket_url)
        host = parsed_url.hostname or "localhost"
        port = parsed_url.port or 8765
        super().__init__(host=host, port=port)
    
    async def vector_search(self, query_text: str, top_k: Optional[int] = None) -> Dict:
        """
        検索を実行
        
        Args:
            query_text: 検索クエリ
            top_k: 取得件数制限（Noneの場合は全件）
            
        Returns:
            (post_id, similarity)のタプルのリスト
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        params = {"query": query_text}
        if top_k is not None:
            params["top_k"] = top_k
        results = await self._send_request("vector_search", params)
        
        # 分割送信されたデータを結合
        data = []
        first = None
        for result in results:
            if first is None:
                first = result.copy()
            data.extend(result["data"])
        
        # 最初のレスポンスにデータを設定して返す
        first["data"] = data
        return first


class TwilogCommand(EmbedCommand):
    """TwilogClientのコマンドライン操作を管理するクラス - EmbedCommandを継承"""
    
    def __init__(self, client: TwilogClient = None):
        # 基底クラスにはTwilogClientをclientを渡す
        super().__init__(client or TwilogClient())
    
    def create_parser(self) -> argparse.ArgumentParser:
        """argparseのparserを作成（基底クラスを拡張）"""
        parser = super().create_parser()
        parser.description = "Twilog検索サーバークライアント"
        
        # 既存のsubparsersを取得して追加
        subparsers = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                subparsers = action
                break
        
        if subparsers:
            # vector_search command (Twilog固有)
            search_parser = subparsers.add_parser('vector_search', help='類似検索を実行')
            search_parser.add_argument('query', help='検索クエリ')
            search_parser.add_argument('-k', '--top-k', type=int, help='取得件数制限')
        
        return parser
    
    async def vector_search(self, args) -> None:
        """vector_searchコマンドの処理"""
        results = await self.client.vector_search(args.query, args.top_k)
        data = results.get("data", [])
        print(f"検索結果: {len(data)}件")
        for i, (post_id, similarity) in enumerate(data[:10], 1):
            print(f"{i:2d}. similarity={similarity:.5f}, post_id={post_id}")


async def main():
    """メイン関数（テスト用）"""
    command = TwilogCommand()
    await command.execute()


if __name__ == "__main__":
    asyncio.run(main())