#!/usr/bin/env python3
"""
Twilogベクトル検索エンジン
"""
from typing import List, Tuple, Generator, Any, Optional
from pathlib import Path
from settings import SearchSettings
from data_csv import TwilogDataAccess
from text_proc import parse_search_terms


class SearchEngine:
    """Twilogベクトル検索クラス"""
    
    def __init__(self, embeddings_dir: str):
        """
        初期化（遅延初期化対応）
        
        Args:
            embeddings_dir: 埋め込みディレクトリのパス
        """
        # パラメータを保存（初期化は後で行う）
        self.embeddings_dir = Path(embeddings_dir)
        
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
    
    def filter_search(self, vector_search_results: List[Tuple[int, float]], search_settings: SearchSettings) -> Generator[Tuple[int, float, dict], None, None]:
        """
        ベクトル検索の結果を絞り込む
        
        Args:
            vector_search_results: ベクトル検索結果
            search_settings: 検索設定
            
        Yields:
            (rank, similarity, post_info)のタプル
        """
        # 重複除去用の辞書
        seen_combinations = {}  # (user, content) -> (post_id, similarity, timestamp, url)
        
        rank = 1
        for post_id, similarity in vector_search_results:
            user = self.post_user_map.get(post_id, '')
            
            # ユーザーフィルタリング条件をチェック
            if not search_settings.user_filter.is_user_allowed(user, self.user_post_counts):
                continue
            
            # 投稿内容を個別取得
            post_info = self.data_access.get_post_content([post_id]).get(post_id, {})
            content = post_info.get('content', '').strip()
            timestamp = post_info.get('timestamp', '')
            url = post_info.get('url', '')
            
            # 日付フィルタリング条件をチェック
            if not search_settings.date_filter.is_date_allowed(timestamp):
                continue
            
            key = (user, content)
            
            # 重複チェック（常に有効）
            if key in seen_combinations:
                # 既存の投稿と同じユーザー・内容の場合、日付が古い方を優先
                _, _, existing_timestamp, _ = seen_combinations[key]
                if timestamp < existing_timestamp:
                    # 現在の投稿の方が古い場合、既存を置き換え
                    seen_combinations[key] = (post_id, similarity, timestamp, url)
                continue
            
            # 新しい組み合わせの場合、追加
            seen_combinations[key] = (post_id, similarity, timestamp, url)
            
            yield rank, similarity, {
                'post_id': post_id,
                'content': content,
                'timestamp': timestamp,
                'url': url,
                'user': user
            }
            
            rank += 1
    
    def is_post_text_match(self, post_id: int, include_terms: List[str], exclude_terms: List[str]) -> bool:
        """
        単一投稿がテキスト条件に合致するかチェック
        
        Args:
            post_id: 投稿ID
            include_terms: 含む条件の検索語リスト
            exclude_terms: 除外条件の検索語リスト
            
        Returns:
            条件に合致するかのbool値
        """
        post_data = self.data_access.posts_data.get(post_id, {})
        content = post_data.get("content", "").lower()
        
        # include_termsの全てが含まれているかチェック
        if include_terms:
            include_match = all(term.lower() in content for term in include_terms)
            if not include_match:
                return False
        
        # exclude_termsのいずれも含まれていないかチェック
        if exclude_terms:
            exclude_match = any(term.lower() in content for term in exclude_terms)
            if exclude_match:
                return False
        
        return True
    
    def vector_search(self, query_vector: Any, top_k: int = None, text_filter: str = "") -> List[Tuple[int, float]]:
        """
        ベクトル検索を実行
        
        Args:
            query_vector: クエリベクトル
            top_k: 取得件数制限
            text_filter: テキストフィルタリング条件（V|T検索用）
            
        Returns:
            (post_id, similarity)のタプルリスト
        """
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
                if not self.is_post_text_match(post_id, text_include_terms, text_exclude_terms):
                    continue
            
            results.append((post_id, similarity))
            
            # top_kに達したら終了
            if top_k is not None and len(results) >= top_k:
                break
        
        return results
    
    def search_similar(self, query_vector: Any, search_settings: SearchSettings, text_filter: str = "") -> List[dict]:
        """
        類似検索を実行（フィルタリング付き）
        
        Args:
            query_vector: クエリベクトル
            search_settings: 検索設定
            text_filter: テキストフィルタリング条件（V|T検索用）
            
        Returns:
            フィルタリング済み検索結果
        """
        # ベクトル検索を実行（テキストフィルタリング付き、top_kは後で適用）
        all_results = self.vector_search(query_vector, top_k=None, text_filter=text_filter)
        
        # フィルタリング（ユーザー・日付フィルタリング）
        filtered_results = []
        top_k = search_settings.top_k.get_top_k()
        
        for result in self.filter_search(all_results, search_settings):
            filtered_results.append(result)
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
        for post_id in self.data_access.posts_data.keys():
            if self.is_post_text_match(post_id, include_terms, exclude_terms):
                post_data = self.data_access.posts_data.get(post_id, {})
                user = self.post_user_map.get(post_id, "")
                results.append({
                    "post_id": post_id,
                    "content": post_data.get("content", ""),
                    "timestamp": post_data.get("timestamp", ""),
                    "url": post_data.get("url", ""),
                    "user": user
                })
        
        # 新しい順でソート
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return results[:limit]
