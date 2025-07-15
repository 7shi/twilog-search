#!/usr/bin/env python3
import asyncio
import sys
import time
import argparse
from pathlib import Path
from typing import Optional
from embed_server import EmbedServer, check_server_status, stop_server, start_daemon, rpc_method
from settings import SearchSettings
from search_engine import SearchEngine


class TwilogServer(EmbedServer):
    """Twilog検索サーバー：embeddings読み込みとベクトル検索機能付き"""
    
    def __init__(self, embeddings_dir: str, reasoning_dir: str, summary_dir: str):
        self.embeddings_dir = Path(embeddings_dir)
        self.reasoning_dir = reasoning_dir
        self.summary_dir = summary_dir
        
        # メタデータからモデル名を取得
        metadata_path = self.embeddings_dir / "meta.json"
        import json
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            model_name = metadata.get("model", "")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RuntimeError(f"メタデータファイルの読み込みに失敗しました: {e}")
        
        super().__init__(model_name)
        
        # SearchEngineは_init_modelで初期化
        self.search_engine = None
    
    async def _init_model(self):
        """モデル初期化とSearchEngine初期化"""
        await super()._init_model()  # 親クラスの初期化を呼び出す
        
        # SearchEngineインスタンスを生成
        self.search_engine = SearchEngine(self._embed_text, str(self.embeddings_dir), self.reasoning_dir, self.summary_dir)
        
        # SearchEngine初期化（embeddings読み込み含む）
        await self.report_progress("SearchEngine初期化開始...")
        start_time = time.monotonic()
        try:
            self.search_engine.initialize()
            init_time = time.monotonic() - start_time
            embeddings_count = len(self.search_engine.content_store.post_ids)
            
            await self.report_progress(f"SearchEngine初期化完了: {embeddings_count}件 ({init_time:.2f}秒)")
        except Exception as e:
            await self.report_progress(f"初期化失敗: {e}")
            raise  # 例外を再発生させて上位で処理される
    
    @rpc_method
    async def vector_search(self, query: str, top_k: int = None, mode: str = "content", weights: list = None):
        """類似検索を実行（Streaming Extensions対応、V|T検索対応）"""
        if not query:
            raise ValueError("query is required")
        
        # SearchEngineにベクトル検索を委譲
        results = self.search_engine.vector_search(query, top_k=top_k, mode=mode, weights=weights)
        
        # Streaming Extensions対応: 結果を分割（2万件ずつ）
        chunk_size = 20000
        total_chunks = (len(results) + chunk_size - 1) // chunk_size if results else 1
        
        chunks = []
        for i in range(max(1, total_chunks)):
            start_idx = i * chunk_size
            end_idx = min(start_idx + chunk_size, len(results))
            chunk_data = results[start_idx:end_idx] if results else []
            chunk = {
                "data": chunk_data,
                "chunk": i + 1,
                "total_chunks": total_chunks,
                "start_rank": start_idx + 1
            }
            chunks.append(chunk)
        
        # Streaming Extensions形式でラップ
        return {"streaming": chunks}
    
    @rpc_method
    async def search_similar(self, query: str, settings: dict = None, mode: str = "content", weights: list = None):
        """類似検索を実行（フィルタリング付き、V|T検索対応）"""
        if not query:
            raise ValueError("query is required")
        
        # SearchSettingsを取得またはデフォルト設定作成
        if settings:
            search_settings = SearchSettings.from_dict(settings)
        else:
            search_settings = SearchSettings()
        
        # top_kのバリデーション
        top_k = search_settings.top_k.get_top_k()
        if top_k < 1 or top_k > 100:
            raise ValueError(f"top_k must be between 1 and 100, got {top_k}")
        
        # SearchEngineに類似検索を委譲
        results = self.search_engine.search_similar(query, search_settings, mode=mode, weights=weights)
        
        # タプルのリストを構造化されたデータに変換
        structured_results = []
        for rank, similarity, post_info in results:
            structured_results.append({
                'rank': rank,
                'score': similarity,
                'post': post_info
            })
        
        return structured_results
    
    @rpc_method
    async def get_user_stats(self, limit: int = 50):
        """ユーザー統計を取得"""
        # limitのバリデーション
        if limit < 1 or limit > 1000:
            raise ValueError(f"limit must be between 1 and 1000, got {limit}")
        
        # SearchEngineに委譲
        return self.search_engine.get_user_stats(limit)
    
    @rpc_method
    async def get_database_stats(self):
        """データベース統計を取得"""
        # SearchEngineに委譲
        return self.search_engine.get_database_stats()
    
    @rpc_method
    async def search_posts_by_text(self, search_term: str, limit: int = 50, source: str = "content"):
        """テキスト検索を実行"""
        if not search_term:
            raise ValueError("search_term is required")
        
        # limitのバリデーション
        if limit < 1 or limit > 1000:
            raise ValueError(f"limit must be between 1 and 1000, got {limit}")
        
        # SearchEngineに委譲
        return self.search_engine.search_posts_by_text(search_term, limit, source)
    
    @rpc_method
    async def suggest_users(self, user_list: list):
        """存在しないユーザーに対して類似ユーザーを提案"""
        if not user_list or not isinstance(user_list, list):
            raise ValueError("user_list must be a non-empty list")
        
        # SearchEngineに委譲
        return self.search_engine.suggest_users(user_list)


async def main():
    parser = argparse.ArgumentParser(description="Twilog Server Daemon Management")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # start command
    start_parser = subparsers.add_parser('start', help='Start the daemon server')
    start_parser.add_argument('-e', '--embeddings-dir', default='embeddings', 
                             help='埋め込みディレクトリ（デフォルト: embeddings）')
    start_parser.add_argument('-r', '--reasoning-dir', default='batch/reasoning',
                             help='reasoningベクトルディレクトリ（デフォルト: batch/reasoning）')
    start_parser.add_argument('-s', '--summary-dir', default='batch/summary',
                             help='summaryベクトルディレクトリ（デフォルト: batch/summary）')
    
    # stop command
    subparsers.add_parser('stop', help='Stop the daemon server')
    
    # status command (default)
    subparsers.add_parser('status', help='Check daemon server status')
    
    # hidden _daemon command for internal use
    daemon_parser = subparsers.add_parser('_daemon', help=argparse.SUPPRESS)
    daemon_parser.add_argument('--embeddings-dir', default='embeddings', 
                              help='埋め込みディレクトリ（デフォルト: embeddings）')
    daemon_parser.add_argument('--reasoning-dir', default='batch/reasoning',
                              help='reasoningベクトルディレクトリ（デフォルト: batch/reasoning）')
    daemon_parser.add_argument('--summary-dir', default='batch/summary',
                              help='summaryベクトルディレクトリ（デフォルト: batch/summary）')
    
    args = parser.parse_args()
    
    if args.command == "_daemon":
        # デーモンモード：メタデータを読み込んでモデル名を取得
        embeddings_dir = Path(args.embeddings_dir)
        metadata_path = embeddings_dir / "meta.json"
        
        try:
            server = TwilogServer(args.embeddings_dir, args.reasoning_dir, args.summary_dir)
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
                "--embeddings-dir", args.embeddings_dir,
                "--reasoning-dir", args.reasoning_dir,
                "--summary-dir", args.summary_dir
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
