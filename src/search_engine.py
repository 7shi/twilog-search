#!/usr/bin/env python3
"""
Twilogベクトル検索エンジン
"""
from typing import List, Tuple, Generator, Any, Optional, Callable
from pathlib import Path
from settings import SearchSettings
from data_csv import TwilogDataAccess
from text_proc import parse_search_terms, parse_pipeline_query


class SearchEngine:
    """Twilogベクトル検索クラス"""
    
    def __init__(self, embeddings_dir: str, embed_func: Callable[[str], Any]):
        """
        初期化（遅延初期化対応）
        
        Args:
            embeddings_dir: 埋め込みディレクトリのパス
            embed_func: テキストをベクトル化する関数
        """
        # パラメータを保存（初期化は後で行う）
        self.embeddings_dir = Path(embeddings_dir)
        self._embed_text = embed_func
        
        # メタデータを読み込み
        metadata_path = self.embeddings_dir / "meta.json"
        self.metadata = self._load_metadata(metadata_path)
        
        # CSVパスを取得
        self.csv_path = self._load_csv_path()
        
        # 初期化フラグ
        self.initialized = False
        
        # 初期化されていない状態での値
        self.data_access: Optional[TwilogDataAccess] = None
        self.post_user_map: dict = {}
        self.user_post_counts: dict = {}
        self.post_ids: List[int] = []
        self.vectors: Optional[Any] = None
    
    def _load_metadata(self, metadata_path: Path) -> dict:
        """メタデータファイルを読み込む"""
        import json
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RuntimeError(f"メタデータファイルの読み込みに失敗しました: {e}")
    
    def get_model_name(self) -> str:
        """モデル名を取得"""
        return self.metadata.get("model", "")
    
    def _load_csv_path(self) -> str:
        """meta.jsonからCSVパスを取得し、絶対パスに変換"""
        csv_relative_path = self.metadata.get("csv_path")
        if not csv_relative_path:
            return ""
        
        # embeddings_dirの親ディレクトリからの相対パスを絶対パスに変換
        embeddings_parent = self.embeddings_dir.parent
        csv_absolute_path = embeddings_parent / csv_relative_path
        return str(csv_absolute_path.resolve())
    
    def initialize(self) -> None:
        """実際の初期化処理を実行"""
        if self.initialized:
            return
        
        # データアクセス層の初期化
        if not self.csv_path:
            raise ValueError("meta.jsonにcsv_pathが見つかりません")
        self.data_access = TwilogDataAccess(self.csv_path)
        
        # ユーザー情報の読み込み
        self.post_user_map, self.user_post_counts = self.data_access.load_user_data()
        
        # 初期化完了フラグ
        self.initialized = True
    
    def _load_embeddings(self) -> None:
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
            self.post_ids, self.vectors = all_post_ids, combined_vectors
        else:
            self.post_ids, self.vectors = [], torch.tensor([])
    
    def is_text_match(self, content: str, include_terms: List[str], exclude_terms: List[str]) -> bool:
        """
        テキスト内容がテキスト条件に合致するかチェック
        
        Args:
            content: 投稿内容
            include_terms: 含む条件の検索語リスト
            exclude_terms: 除外条件の検索語リスト
            
        Returns:
            条件に合致するかのbool値
        """
        content_lower = content.lower()
        
        # include_termsの全てが含まれているかチェック
        if include_terms:
            include_match = all(term.lower() in content_lower for term in include_terms)
            if not include_match:
                return False
        
        # exclude_termsのいずれも含まれていないかチェック
        if exclude_terms:
            exclude_match = any(term.lower() in content_lower for term in exclude_terms)
            if exclude_match:
                return False
        
        return True
    
    def vector_search(self, query: str, top_k: int = None) -> List[Tuple[int, float]]:
        """
        ベクトル検索を実行
        
        Args:
            query: クエリ文字列（V|T形式対応）
            top_k: 取得件数制限
            
        Returns:
            (post_id, similarity)のタプルリスト
        """
        # V|T検索の解析
        vector_query, text_filter = parse_pipeline_query(query)
        
        # ベクトル検索クエリが空の場合はエラー
        if not vector_query:
            raise ValueError("Vector query is empty: vector_search requires a vector query part")
        
        # ベクトル検索クエリをベクトル化
        query_vector = self._embed_text(vector_query)
        # embeddings遅延読み込み
        if self.vectors is None:
            self._load_embeddings()
        
        if self.vectors is None or len(self.vectors) == 0:
            return []
        
        
        # コサイン類似度の計算
        import torch.nn.functional as F
        similarities = F.cosine_similarity(self.vectors, query_vector, dim=1)
        
        # 類似度でソート（降順）
        import torch
        sorted_indices = torch.argsort(similarities, descending=True)
        
        # テキストフィルタリング条件を準備
        text_include_terms = []
        text_exclude_terms = []
        if text_filter:
            text_include_terms, text_exclude_terms = parse_search_terms(text_filter)
        
        # 結果を作成（フィルタリングしながらtop_kまで収集）
        results = []
        for idx in sorted_indices:
            post_id = self.post_ids[idx.item()]
            similarity = similarities[idx].item()
            
            # テキストフィルタリングを適用
            if text_filter:
                post_data = self.data_access.posts_data.get(post_id, {})
                content = post_data.get("content", "")
                if not self.is_text_match(content, text_include_terms, text_exclude_terms):
                    continue
            
            results.append((post_id, similarity))
            
            # top_kに達したら終了
            if top_k is not None and len(results) >= top_k:
                break
        
        return results
    
    def _generate_text_results(self, text_filter: str) -> Generator[Tuple[dict, float], None, None]:
        """
        テキスト検索結果を(post_info, similarity)形式で生成
        
        Args:
            text_filter: テキストフィルタリング条件
            
        Yields:
            (post_info, similarity)のタプル
        """
        text_results = self.search_posts_by_text(text_filter, limit=10000)
        for result in text_results:
            yield result, 1.0
    
    def _generate_vector_results(self, vector_query: str) -> Generator[Tuple[dict, float], None, None]:
        """
        ベクトル検索結果を(post_info, similarity)形式で生成
        
        Args:
            vector_query: ベクトル検索クエリ
            
        Yields:
            (post_info, similarity)のタプル
        """
        all_results = self.vector_search(vector_query, top_k=None)
        for post_id, similarity in all_results:
            user = self.post_user_map.get(post_id, '')
            post_data = self.data_access.get_post_content([post_id]).get(post_id, {})
            post_info = {
                'post_id': post_id,
                'content': post_data.get('content', '').strip(),
                'timestamp': post_data.get('timestamp', ''),
                'url': post_data.get('url', ''),
                'user': user
            }
            yield post_info, similarity
    
    def search_similar(self, query: str, search_settings: SearchSettings) -> List[Tuple[int, float, dict]]:
        """
        類似検索を実行（フィルタリング付き）
        
        Args:
            query: クエリ文字列（V|T形式対応）
            search_settings: 検索設定
            
        Returns:
            (rank, similarity, post_info)のタプルリスト
        """
        # V|T検索の解析
        vector_query, text_filter = parse_pipeline_query(query)
        
        # 結果ジェネレーターの選択
        if not vector_query:
            if not text_filter:
                raise ValueError("Empty query: both vector and text parts are empty")
            results_generator = self._generate_text_results(text_filter)
        else:
            results_generator = self._generate_vector_results(vector_query)
        
        # 統一されたフィルタリングループ
        filtered_results = []
        top_k = search_settings.top_k.get_top_k()
        seen_combinations = {}  # (user, content) -> (post_id, similarity, timestamp, url)
        rank = 1
        
        for post_info, similarity in results_generator:
            # フィルタリング条件をチェック
            user = post_info.get('user', '')
            timestamp = post_info.get('timestamp', '')
            
            # ユーザーフィルタリング条件をチェック
            if not search_settings.user_filter.is_user_allowed(user, self.user_post_counts):
                continue
            
            # 日付フィルタリング条件をチェック
            if not search_settings.date_filter.is_date_allowed(timestamp):
                continue
            
            # 重複チェック（常に有効）
            content = post_info['content']
            url = post_info['url']
            post_id = post_info['post_id']
            key = (user, content)
            
            if key in seen_combinations:
                # 既存の投稿と同じユーザー・内容の場合、日付が古い方を優先
                _, _, existing_timestamp, _ = seen_combinations[key]
                if timestamp < existing_timestamp:
                    # 現在の投稿の方が古い場合、既存を置き換え
                    seen_combinations[key] = (post_id, similarity, timestamp, url)
                continue
            
            # 新しい組み合わせの場合、追加
            seen_combinations[key] = (post_id, similarity, timestamp, url)
            
            filtered_results.append((rank, similarity, post_info))
            
            rank += 1
            if len(filtered_results) >= top_k:
                break
        
        return filtered_results
    
    def get_user_stats(self, limit: int = 50) -> List[dict]:
        """
        ユーザー統計を取得
        
        Args:
            limit: 取得する最大件数
            
        Returns:
            ユーザー統計リスト
        """
        user_stats = []
        for user, count in self.user_post_counts.items():
            user_stats.append({"user": user, "post_count": count})
        
        # 投稿数順でソート
        user_stats.sort(key=lambda x: x["post_count"], reverse=True)
        
        return user_stats[:limit]
    
    def get_database_stats(self) -> dict:
        """
        データベース統計を取得
        
        Returns:
            データベース統計辞書
        """
        total_posts = len(self.data_access.posts_data)
        total_users = len(self.user_post_counts)
        
        # 日付範囲を取得
        timestamps = []
        for post_data in self.data_access.posts_data.values():
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
    
    def search_posts_by_text(self, search_term: str, limit: int = 50) -> List[dict]:
        """
        テキスト検索を実行
        
        Args:
            search_term: 検索語
            limit: 取得する最大件数
            
        Returns:
            検索結果リスト
        """
        # 検索語をパース
        include_terms, exclude_terms = parse_search_terms(search_term)
        
        # 結果を構築
        results = []
        for post_id, post_data in self.data_access.posts_data.items():
            content = post_data.get("content", "")
            if self.is_text_match(content, include_terms, exclude_terms):
                user = self.post_user_map.get(post_id, "")
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
