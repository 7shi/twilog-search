#!/usr/bin/env python3
"""
Twilog検索サーバー用クライアント

TwilogServerの全メソッドをサポート:
- vector_search: ベクトル検索
- search_similar: フィルタリング付き類似検索
- get_user_stats: ユーザー統計
- get_database_stats: データベース統計
- search_posts_by_text: テキスト検索
- get_status: サーバー状態確認
- embed_text: テキストベクトル化
"""
import asyncio
import argparse
from typing import Dict, Optional
from urllib.parse import urlparse
from embed_client import EmbedClient, EmbedCommand
from settings import SearchSettings


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
        ベクトル検索を実行
        
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
    
    async def search_similar(self, query_text: str, search_settings: Optional[SearchSettings] = None, top_k: Optional[int] = None) -> list:
        """
        類似検索を実行（フィルタリング付き）
        
        Args:
            query_text: 検索クエリ
            search_settings: 検索設定
            top_k: 取得件数制限（デフォルト: 10）
            
        Returns:
            (rank, similarity, post_info)のタプルのリスト
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        params = {"query": query_text}
        if top_k is not None:
            params["top_k"] = top_k
        if search_settings is not None:
            params["search_settings"] = search_settings.to_dict()
        return await self._send_request("search_similar", params)
    
    async def get_user_stats(self, limit: Optional[int] = None) -> list:
        """
        ユーザー統計を取得
        
        Args:
            limit: 取得件数制限（デフォルト: 50）
            
        Returns:
            {"user": str, "post_count": int}の辞書のリスト
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        params = {}
        if limit is not None:
            params["limit"] = limit
        return await self._send_request("get_user_stats", params)
    
    async def get_database_stats(self) -> dict:
        """
        データベース統計を取得
        
        Returns:
            統計情報の辞書
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        return await self._send_request("get_database_stats", {})
    
    async def search_posts_by_text(self, search_term: str, limit: Optional[int] = None) -> list:
        """
        テキスト検索を実行
        
        Args:
            search_term: 検索文字列
            limit: 取得件数制限（デフォルト: 50）
            
        Returns:
            投稿情報の辞書のリスト
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        params = {"search_term": search_term}
        if limit is not None:
            params["limit"] = limit
        return await self._send_request("search_posts_by_text", params)


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
            # vector_search command
            search_parser = subparsers.add_parser('vector_search', help='ベクトル検索を実行')
            search_parser.add_argument('query', help='検索クエリ')
            search_parser.add_argument('-k', '--top-k', type=int, help='取得件数制限')
            
            # search_similar command
            similar_parser = subparsers.add_parser('search_similar', help='類似検索を実行（フィルタリング付き）')
            similar_parser.add_argument('query', help='検索クエリ')
            similar_parser.add_argument('-k', '--top-k', type=int, help='取得件数制限')
            
            # get_user_stats command
            user_stats_parser = subparsers.add_parser('get_user_stats', help='ユーザー統計を取得')
            user_stats_parser.add_argument('-l', '--limit', type=int, help='取得件数制限')
            
            # get_database_stats command
            subparsers.add_parser('get_database_stats', help='データベース統計を取得')
            
            # search_posts_by_text command
            text_search_parser = subparsers.add_parser('search_posts_by_text', help='テキスト検索を実行')
            text_search_parser.add_argument('search_term', help='検索文字列')
            text_search_parser.add_argument('-l', '--limit', type=int, help='取得件数制限')
        
        return parser
    
    async def vector_search(self, args) -> None:
        """vector_searchコマンドの処理"""
        results = await self.client.vector_search(args.query, args.top_k)
        data = results.get("data", [])
        print(f"検索結果: {len(data)}件")
        for i, (post_id, similarity) in enumerate(data[:10], 1):
            print(f"{i:2d}. similarity={similarity:.5f}, post_id={post_id}")
    
    async def search_similar(self, args) -> None:
        """search_similarコマンドの処理"""
        results = await self.client.search_similar(args.query, args.top_k)
        print(f"類似検索結果: {len(results)}件")
        for rank, similarity, post_info in results[:10]:
            user = post_info.get('user', 'unknown')
            content = post_info.get('content', '')[:100]  # 最初の100文字のみ表示
            timestamp = post_info.get('timestamp', '')
            print(f"{rank:2d}. {similarity:.5f} - @{user} [{timestamp}]")
            print(f"    {content}...")
    
    async def get_user_stats(self, args) -> None:
        """get_user_statsコマンドの処理"""
        results = await self.client.get_user_stats(args.limit)
        print(f"ユーザー統計: {len(results)}人")
        for i, stat in enumerate(results[:20], 1):
            print(f"{i:2d}. {stat['user']}: {stat['post_count']}投稿")
    
    async def get_database_stats(self, args) -> None:
        """get_database_statsコマンドの処理"""
        results = await self.client.get_database_stats()
        print("データベース統計:")
        print(f"  総投稿数: {results['total_posts']:,}件")
        print(f"  総ユーザー数: {results['total_users']:,}人")
        date_range = results.get('date_range', {})
        if date_range:
            print(f"  データ期間: {date_range.get('earliest', '')} ～ {date_range.get('latest', '')}")
    
    async def search_posts_by_text(self, args) -> None:
        """search_posts_by_textコマンドの処理"""
        results = await self.client.search_posts_by_text(args.search_term, args.limit)
        print(f"テキスト検索結果: {len(results)}件")
        for i, post in enumerate(results[:10], 1):
            user = post.get('user', 'unknown')
            content = post.get('content', '')[:100]  # 最初の100文字のみ表示
            timestamp = post.get('timestamp', '')
            print(f"{i:2d}. @{user} [{timestamp}]")
            print(f"    {content}...")


async def main():
    """メイン関数（テスト用）"""
    command = TwilogCommand()
    await command.execute()


if __name__ == "__main__":
    asyncio.run(main())