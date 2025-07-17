#!/usr/bin/env python3
"""
Twilog検索サーバー用クライアント

TwilogServerの全メソッドをサポート:
- vector_search: ベクトル検索
- search_similar: フィルタリング付き類似検索
- get_user_stats: ユーザー統計
- get_database_stats: データベース統計
- search_posts_by_text: テキスト検索
- get_user_list: ユーザー一覧取得
- get_status: サーバー状態確認
- embed_text: テキストベクトル化
"""
import asyncio
import argparse
from typing import Dict, Optional
from urllib.parse import urlparse
from embed_client import EmbedClient, EmbedCommand, rpc_method
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
    
    @rpc_method
    async def vector_search(self, query_text: str, top_k: Optional[int] = None, mode: str = "content", weights: Optional[list] = None) -> Dict:
        """
        ベクトル検索を実行
        
        Args:
            query_text: 検索クエリ
            top_k: 取得件数制限（Noneの場合は全件）
            mode: 検索モード ("content", "reasoning", "summary", "average", "maximum", "minimum")
            weights: 重み付けモード用の重み（合計1.0）
            
        Returns:
            (post_id, similarity)のタプルのリスト
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        params = {"query": query_text, "mode": mode}
        if top_k is not None:
            params["top_k"] = top_k
        if weights is not None:
            params["weights"] = weights
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
    
    @rpc_method
    async def search_similar(self, query_text: str, search_settings: Optional[SearchSettings] = None, mode: str = "content", weights: Optional[list] = None) -> list:
        """
        類似検索を実行（フィルタリング付き）
        
        Args:
            query_text: 検索クエリ
            search_settings: 検索設定（top_k含む）
            mode: 検索モード ("content", "reasoning", "summary", "average", "maximum", "minimum")
            weights: 重み付けモード用の重み（合計1.0）
            
        Returns:
            構造化された検索結果のリスト
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        params = {"query": query_text, "mode": mode}
        if search_settings is not None:
            params["settings"] = search_settings.to_dict()
        if weights is not None:
            params["weights"] = weights
        return await self._send_request("search_similar", params)
    
    @rpc_method
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
    
    @rpc_method
    async def get_database_stats(self) -> dict:
        """
        データベース統計を取得
        
        Returns:
            統計情報の辞書
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        return await self._send_request("get_database_stats", {})
    
    @rpc_method
    async def search_posts_by_text(self, search_term: str, limit: Optional[int] = None, source: str = "content") -> list:
        """
        テキスト検索を実行
        
        Args:
            search_term: 検索文字列
            limit: 取得件数制限（デフォルト: 50）
            source: 検索対象ソース ("content", "reasoning", "summary")
            
        Returns:
            投稿情報の辞書のリスト
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        params = {"search_term": search_term, "source": source}
        if limit is not None:
            params["limit"] = limit
        return await self._send_request("search_posts_by_text", params)
    
    @rpc_method
    async def get_user_list(self) -> list:
        """
        全ユーザーのリストを取得
        
        Returns:
            ユーザー名のリスト
            
        Raises:
            RuntimeError: サーバーエラーまたは通信エラー
        """
        return await self._send_request("get_user_list", {})


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
            search_parser.add_argument('-m', '--mode', default='content', 
                                     choices=['content', 'reasoning', 'summary', 'average', 'maximum', 'minimum'],
                                     help='検索モード (デフォルト: content)')
            search_parser.add_argument('-w', '--weights', nargs='+', type=float, 
                                     help='重み付けモード用の重み（例: 0.7 0.2 0.1）')
            
            # search_similar command
            similar_parser = subparsers.add_parser('search_similar', help='類似検索を実行（フィルタリング付き）')
            similar_parser.add_argument('query', help='検索クエリ')
            similar_parser.add_argument('-k', '--top-k', type=int, help='取得件数制限')
            similar_parser.add_argument('-m', '--mode', default='content', 
                                       choices=['content', 'reasoning', 'summary', 'average', 'maximum', 'minimum'],
                                       help='検索モード (デフォルト: content)')
            similar_parser.add_argument('-w', '--weights', nargs='+', type=float, 
                                       help='重み付けモード用の重み（例: 0.7 0.2 0.1）')
            
            # get_user_stats command
            user_stats_parser = subparsers.add_parser('get_user_stats', help='ユーザー統計を取得')
            user_stats_parser.add_argument('-l', '--limit', type=int, help='取得件数制限')
            
            # get_database_stats command
            subparsers.add_parser('get_database_stats', help='データベース統計を取得')
            
            # search_posts_by_text command
            text_search_parser = subparsers.add_parser('search_posts_by_text', help='テキスト検索を実行')
            text_search_parser.add_argument('search_term', help='検索文字列')
            text_search_parser.add_argument('-l', '--limit', type=int, help='取得件数制限')
            text_search_parser.add_argument('-s', '--source', default='content', 
                                           choices=['content', 'reasoning', 'summary'],
                                           help='検索対象ソース (デフォルト: content)')
            
            # get_user_list command
            subparsers.add_parser('get_user_list', help='ユーザー一覧を取得')
        
        return parser
    
    # 以下のrpc_methodメソッドは、MCPサーバー（mcp/src/index.ts）の出力形式と同期している
    # 整形テキスト形式での統一出力により、CLI・MCP両方で一貫した表示を提供
    
    @rpc_method
    async def get_status(self, args) -> None:
        """get_statusコマンドの処理"""
        results = await self.client.get_status()
        
        status_icon = "🟢" if results.get('ready', False) else "🔴"
        status_text = "稼働中" if results.get('ready', False) else "停止中"
        
        print(f"{status_icon} Twilog Server Status\n")
        print(f"状態: {status_text}")
        print(f"サーバータイプ: {results.get('server_type', 'Unknown')}")
        
        if results.get('model'):
            print(f"モデル: {results['model']}")
        
        if results.get('data_stats'):
            print("\n📊 データ統計:")
            data_stats = results['data_stats']
            print(f"・投稿数: {data_stats.get('total_posts', 0):,}件")
            print(f"・ユーザー数: {data_stats.get('total_users', 0):,}人")
            if data_stats.get('total_summaries'):
                print(f"・要約数: {data_stats['total_summaries']:,}件")
            if data_stats.get('total_tags'):
                print(f"・タグ数: {data_stats['total_tags']:,}件")

    
    @rpc_method
    async def vector_search(self, args) -> None:
        """vector_searchコマンドの処理"""
        results = await self.client.vector_search(args.query, args.top_k, args.mode, args.weights)
        data = results.get("data", [])
        print(f"🔍 ベクトル検索結果: {len(data)}件 (mode: {args.mode})\n")
        
        for i, (post_id, similarity) in enumerate(data, 1):
            print(f"{i}. similarity={similarity:.5f}, post_id={post_id}")
    
    @rpc_method
    async def search_similar(self, args) -> None:
        """search_similarコマンドの処理"""
        search_settings = None
        if args.top_k is not None:
            search_settings = SearchSettings(args.top_k)
        results = await self.client.search_similar(args.query, search_settings, args.mode, args.weights)
        
        print(f"🔍 検索結果: {len(results)}件 (クエリ: \"{args.query}\")\n")
        
        for i, result in enumerate(results, 1):
            post = result['post']
            score = result['score']
            
            print(f"{i}. [{score:.3f}] @{post['user']} ({post['timestamp']}) {post['url']}")
            
            # 投稿内容の処理（改行保持、空行詰め）
            import re
            content = re.sub(r'\n\s*\n', '\n', post['content']).strip()
            print(f"   {content}\n")
    
    @rpc_method
    async def get_user_stats(self, args) -> None:
        """get_user_statsコマンドの処理"""
        results = await self.client.get_user_stats(args.limit)
        print(f"👥 ユーザー別投稿統計 (上位{len(results)}人)\n")
        
        for i, stat in enumerate(results, 1):
            post_count = f"{stat['post_count']:,}"
            print(f"{i}. {stat['user']}: {post_count}投稿")
    
    @rpc_method
    async def get_database_stats(self, args) -> None:
        """get_database_statsコマンドの処理"""
        results = await self.client.get_database_stats()
        print("📊 データベース統計\n")
        print(f"総投稿数: {results['total_posts']:,}件")
        print(f"総ユーザー数: {results['total_users']:,}人")
        date_range = results.get('date_range', {})
        if date_range:
            print(f"データ期間: {date_range.get('earliest', '')} ～ {date_range.get('latest', '')}")
    
    @rpc_method
    async def search_posts_by_text(self, args) -> None:
        """search_posts_by_textコマンドの処理"""
        results = await self.client.search_posts_by_text(args.search_term, args.limit, args.source)
        print(f"📝 テキスト検索結果: {len(results)}件 (検索語: \"{args.search_term}\")\n")
        
        for i, post in enumerate(results, 1):
            user = post.get('user', 'unknown')
            content = post.get('content', '')
            timestamp = post.get('timestamp', '')
            
            print(f"{i}. @{user} ({timestamp})")
            
            # 投稿内容の処理（改行保持、空行詰め）
            import re
            content = re.sub(r'\n\s*\n', '\n', content).strip()
            print(f"   {content}\n")
    
    @rpc_method
    async def get_user_list(self, args) -> None:
        """get_user_listコマンドの処理"""
        results = await self.client.get_user_list()
        total_users = len(results)
        print(f"👤 ユーザー一覧: 総数 {total_users:,}人\n")
        
        # 最初の10件を表示
        for i, user in enumerate(results[:10], 1):
            print(f"{i}. {user}")
        
        # 10件超過の場合は縦点を表示
        if total_users > 10:
            print("   ...")
            print(f"\n(総数: {total_users:,}人)")


async def main():
    """メイン関数（テスト用）"""
    command = TwilogCommand()
    await command.execute()

if __name__ == "__main__":
    asyncio.run(main())
