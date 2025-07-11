#!/usr/bin/env python3
import asyncio
import sys
import time
import argparse
from pathlib import Path
from embed_server import EmbedServer, check_server_status, stop_server, start_daemon
from settings import SearchSettings
from search_engine import SearchEngine


class TwilogServer(EmbedServer):
    """Twilog検索サーバー：embeddings読み込みとベクトル検索機能付き"""
    
    def __init__(self, embeddings_dir: str):
        self.embeddings_dir = Path(embeddings_dir)
        
        # SearchEngineインスタンスを生成（初期化は後で行う）
        self.search_engine = SearchEngine(self.embeddings_dir)
        
        # SearchEngineからモデル名を取得
        model_name = self.search_engine.get_model_name()
        
        super().__init__(model_name)
    
    async def _init_model(self):
        """モデル初期化とSearchEngine初期化"""
        await super()._init_model()  # 親クラスの初期化を呼び出す
        
        # SearchEngine初期化（embeddings読み込み含む）
        await self.report_progress("SearchEngine初期化開始...")
        start_time = time.monotonic()
        try:
            self.search_engine.initialize()
            init_time = time.monotonic() - start_time
            embeddings_count = len(self.search_engine.post_ids)
            await self.report_progress(f"SearchEngine初期化完了: {embeddings_count}件 ({init_time:.2f}秒)")
        except Exception as e:
            await self.report_progress(f"初期化失敗: {e}")
            raise  # 例外を再発生させて上位で処理される
    
    async def vector_search(self, params: dict = None):
        """類似検索を実行（Streaming Extensions対応）"""
        query = params.get("query") if params else None
        if not query:
            raise ValueError("Invalid params: query is required")
        
        # クエリをベクトル化
        query_vector = self._embed_text(query)
        
        # SearchEngineにベクトル検索を委譲
        chunks = self.search_engine.vector_search(query_vector, params)
        
        # Streaming Extensions形式でラップ
        return {"streaming": chunks}
    
    async def search_similar(self, params: dict = None):
        """類似検索を実行（フィルタリング付き）"""
        query = params.get("query") if params else None
        if not query:
            raise ValueError("Invalid params: query is required")
        
        # SearchSettingsを取得またはデフォルト設定作成
        search_settings_dict = params.get("settings") if params else None
        if search_settings_dict:
            search_settings = SearchSettings.from_dict(search_settings_dict)
        else:
            search_settings = SearchSettings()
        
        # top_kのバリデーション
        top_k = search_settings.top_k.get_top_k()
        if top_k < 1 or top_k > 100:
            raise ValueError(f"top_k must be between 1 and 100, got {top_k}")
        
        # クエリをベクトル化
        query_vector = self._embed_text(query)
        
        # SearchEngineに類似検索を委譲
        results = self.search_engine.search_similar(query_vector, search_settings)
        
        # タプルのリストを構造化されたデータに変換
        structured_results = []
        for rank, similarity, post_info in results:
            structured_results.append({
                'rank': rank,
                'score': similarity,
                'post': post_info
            })
        
        return structured_results
    
    async def get_user_stats(self, params: dict = None):
        """ユーザー統計を取得"""
        limit = params.get("limit", 50) if params else 50
        
        # SearchEngineに委譲
        return self.search_engine.get_user_stats(limit)
    
    async def get_database_stats(self, params: dict = None):
        """データベース統計を取得"""
        # SearchEngineに委譲
        return self.search_engine.get_database_stats()
    
    async def search_posts_by_text(self, params: dict = None):
        """テキスト検索を実行"""
        search_term = params.get("search_term") if params else None
        if not search_term:
            raise ValueError("Invalid params: search_term is required")
        
        limit = params.get("limit", 50) if params else 50
        
        # SearchEngineに委譲
        return self.search_engine.search_posts_by_text(search_term, limit)


async def main():
    parser = argparse.ArgumentParser(description="Twilog Server Daemon Management")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # start command
    start_parser = subparsers.add_parser('start', help='Start the daemon server')
    start_parser.add_argument('-e', '--embeddings-dir', default='embeddings', 
                             help='埋め込みディレクトリ（デフォルト: embeddings）')
    
    # stop command
    subparsers.add_parser('stop', help='Stop the daemon server')
    
    # status command (default)
    subparsers.add_parser('status', help='Check daemon server status')
    
    # hidden _daemon command for internal use
    daemon_parser = subparsers.add_parser('_daemon', help=argparse.SUPPRESS)
    daemon_parser.add_argument('--embeddings-dir', default='embeddings', 
                              help='埋め込みディレクトリ（デフォルト: embeddings）')
    
    args = parser.parse_args()
    
    if args.command == "_daemon":
        # デーモンモード：メタデータを読み込んでモデル名を取得
        embeddings_dir = Path(args.embeddings_dir)
        metadata_path = embeddings_dir / "meta.json"
        
        try:
            server = TwilogServer(args.embeddings_dir)
            await server.start_server()
        except (FileNotFoundError, KeyError, RuntimeError, ValueError) as e:
            print(f"サーバー起動エラー: {e}")
            return
    elif args.command == "start":
        # 起動処理
        status = await check_server_status()
        if status:
            print(f"サーバーは既に起動中です: {status}")
        else:
            print("サーバーを起動します...")
            
            # デーモン起動引数を作成
            daemon_args = [
                sys.executable, __file__, "_daemon",
                "--embeddings-dir", args.embeddings_dir
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
