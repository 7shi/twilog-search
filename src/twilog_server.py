#!/usr/bin/env python3
import asyncio
import json
import os
import sys
import time
import argparse
from pathlib import Path
from typing import Optional, Any, List, Tuple
from embed_server import EmbedServer, check_server_status, stop_server, start_daemon
from search_engine import SearchEngine
from settings import SearchSettings


class TwilogServer(EmbedServer):
    """Twilog検索サーバー：embeddings読み込みとベクトル検索機能付き"""
    
    def __init__(self, embeddings_dir: str, metadata: dict):
        self.embeddings_dir = Path(embeddings_dir)
        self.metadata = metadata
        model_name = metadata["model"]  # modelが存在しない場合はエラー
        
        super().__init__(model_name)
        self.post_ids: List[int] = []
        self.vectors: Optional[Any] = None
        self.search_engine: Optional[SearchEngine] = None
    
    def _load_embeddings(self) -> Tuple[List[int], Any]:
        """分割された埋め込みファイルを読み込む"""
        import torch
        import safetensors.torch
        
        all_post_ids = []
        all_vectors = []
        
        # チャンク数を取得
        chunks = self.metadata["chunks"]
        
        # 存在するファイルのリストを作成
        existing_files = []
        for chunk_id in range(chunks):
            chunk_file = self.embeddings_dir / f"{chunk_id:04d}.safetensors"
            if chunk_file.exists():
                existing_files.append((chunk_id, chunk_file))
        
        # 進捗表示付きで読み込み
        for chunk_id, chunk_file in existing_files:
            # safetensorsファイルを読み込み
            data = safetensors.torch.load_file(chunk_file)
            post_ids = data["post_ids"].tolist()
            vectors = data["vectors"]
            
            all_post_ids.extend(post_ids)
            all_vectors.append(vectors)
        
        # 全ベクトルを結合
        if all_vectors:
            combined_vectors = torch.cat(all_vectors, dim=0)
            return all_post_ids, combined_vectors
        else:
            return [], torch.tensor([])

    def _load_csv_path(self) -> str:
        """meta.jsonからCSVパスを取得し、絶対パスに変換"""
        csv_relative_path = self.metadata.get("csv_path")
        if not csv_relative_path:
            raise ValueError("meta.jsonにcsv_pathが見つかりません")
        
        # embeddings_dirの親ディレクトリからの相対パスを絶対パスに変換
        embeddings_parent = self.embeddings_dir.parent
        csv_absolute_path = embeddings_parent / csv_relative_path
        return str(csv_absolute_path.resolve())
    
    def _init_search_engine(self):
        """SearchEngineインスタンスの初期化"""
        csv_path = self._load_csv_path()
        self.search_engine = SearchEngine(csv_path)
    
    async def _init_model(self):
        """モデル初期化とembeddings読み込み"""
        await super()._init_model()  # 親クラスの初期化を呼び出す
        
        # embeddings読み込みを追加（例外は上位に伝播）
        await self.report_progress("embeddings読み込み開始...")
        start_time = time.monotonic()
        try:
            self.post_ids, self.vectors = self._load_embeddings()
            embeddings_time = time.monotonic() - start_time
            await self.report_progress(f"embeddings読み込み完了: {len(self.post_ids)}件 ({embeddings_time:.2f}秒)")
            
            # SearchEngine初期化
            await self.report_progress("SearchEngine初期化開始...")
            search_start_time = time.monotonic()
            self._init_search_engine()
            search_time = time.monotonic() - search_start_time
            await self.report_progress(f"SearchEngine初期化完了 ({search_time:.2f}秒)")
        except Exception as e:
            await self.report_progress(f"初期化失敗: {e}")
            raise  # 例外を再発生させて上位で処理される
    
    async def vector_search(self, params: dict = None):
        """類似検索を実行（Streaming Extensions対応）"""
        if not self.init_completed:
            raise RuntimeError("モデルがまだ初期化されていません")
        
        query = params.get("query") if params else None
        if not query:
            raise ValueError("Invalid params: query is required")
        
        if self.vectors is None or len(self.vectors) == 0:
            # 空結果の場合もチャンク形式で返却
            return [{
                "data": [],
                "chunk": 1,
                "total_chunks": 1,
                "start_rank": 1,
            }]
        
        top_k = params.get("top_k", None) if params else None
        
        # クエリをベクトル化
        query_vector = self._embed_text(query)
        
        # コサイン類似度の計算
        import torch.nn.functional as F
        similarities = F.cosine_similarity(self.vectors, query_vector, dim=1)
        
        # 類似度でソート（降順）
        import torch
        sorted_indices = torch.argsort(similarities, descending=True)
        
        # top_kがNoneの場合は全件、指定されている場合は制限
        if top_k is None:
            target_indices = sorted_indices
        else:
            target_indices = sorted_indices[:top_k]
        
        # 結果を作成
        results = []
        for idx in target_indices:
            post_id = self.post_ids[idx.item()]
            similarity = similarities[idx].item()
            results.append((post_id, similarity))
        
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
        
        return chunks
    
    async def search_similar(self, params: dict = None):
        """類似検索を実行（フィルタリング付き）"""
        if not self.init_completed:
            raise RuntimeError("モデルがまだ初期化されていません")
        
        if not self.search_engine:
            raise RuntimeError("SearchEngineが初期化されていません")
        
        query = params.get("query") if params else None
        if not query:
            raise ValueError("Invalid params: query is required")
        
        # SearchSettingsを取得またはデフォルト設定作成
        search_settings_dict = params.get("search_settings") if params else None
        if search_settings_dict:
            search_settings = SearchSettings.from_dict(search_settings_dict)
        else:
            search_settings = SearchSettings()
        
        # ベクトル検索を実行
        vector_search_results = await self.vector_search(params)
        
        # チャンク形式の結果を統合
        all_results = []
        for chunk in vector_search_results:
            all_results.extend(chunk.get("data", []))
        
        # SearchEngineでフィルタリング
        filtered_results = []
        top_k = search_settings.top_k.get_top_k()
        
        for result in self.search_engine.filter_search(all_results, search_settings):
            filtered_results.append(result)
            if len(filtered_results) >= top_k:
                break
        
        return filtered_results
    
    async def get_user_stats(self, params: dict = None):
        """ユーザー統計を取得"""
        if not self.search_engine:
            raise RuntimeError("SearchEngineが初期化されていません")
        
        limit = params.get("limit", 50) if params else 50
        
        # SearchEngineからユーザー統計を取得
        user_stats = []
        for user, count in self.search_engine.user_post_counts.items():
            user_stats.append({"user": user, "post_count": count})
        
        # 投稿数順でソート
        user_stats.sort(key=lambda x: x["post_count"], reverse=True)
        
        return user_stats[:limit]
    
    async def get_database_stats(self, params: dict = None):
        """データベース統計を取得"""
        if not self.search_engine:
            raise RuntimeError("SearchEngineが初期化されていません")
        
        # SearchEngineからデータ統計を取得
        total_posts = len(self.search_engine.data_access.posts_data)
        total_users = len(self.search_engine.user_post_counts)
        
        # 日付範囲を取得（簡易実装）
        timestamps = []
        for post_data in self.search_engine.data_access.posts_data.values():
            if post_data.get("timestamp"):
                timestamps.append(post_data["timestamp"])
        
        timestamps.sort()
        earliest = timestamps[0] if timestamps else ""
        latest = timestamps[-1] if timestamps else ""
        
        return {
            "total_posts": total_posts,
            "total_users": total_users,
            "date_range": {
                "earliest": earliest,
                "latest": latest
            }
        }
    
    async def search_posts_by_text(self, params: dict = None):
        """テキスト検索を実行"""
        if not self.search_engine:
            raise RuntimeError("SearchEngineが初期化されていません")
        
        search_term = params.get("search_term") if params else None
        if not search_term:
            raise ValueError("Invalid params: search_term is required")
        
        limit = params.get("limit", 50) if params else 50
        
        # SearchEngineのデータから検索
        results = []
        for post_id, post_data in self.search_engine.data_access.posts_data.items():
            content = post_data.get("content", "")
            if search_term.lower() in content.lower():
                user = self.search_engine.post_user_map.get(post_id, "")
                results.append({
                    "post_id": post_id,
                    "content": content,
                    "timestamp": post_data.get("timestamp", ""),
                    "url": post_data.get("url", ""),
                    "user": user
                })
        
        # 新しい順でソート
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return results[:limit]
    
    async def get_status(self, params: dict = None):
        """ステータスを取得"""
        response = await super().get_status(params)
        response["embeddings_loaded"] = len(self.post_ids) if self.post_ids else 0
        response["search_engine_ready"] = self.search_engine is not None
        return response


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
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            model_name = metadata["model"]
            
            server = TwilogServer(args.embeddings_dir, metadata)
            await server.start_server()
        except (FileNotFoundError, KeyError) as e:
            print(f"メタデータファイルエラー: {e}")
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
