#!/usr/bin/env python3
"""
Twilogベクトル検索エンジン
"""
from typing import List, Dict, Tuple, Generator, Any, Optional, Callable
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
        self.user_list: List[str] = []
        self.post_ids: List[int] = []
        self.vectors: Optional[Any] = None
        
        # ハイブリッド検索用データ
        self.content_vectors: Optional[Any] = None
        self.reasoning_vectors: Optional[Any] = None
        self.summary_vectors: Optional[Any] = None
        self.tags_data: Dict[int, dict] = {}
        self.tag_index: Dict[str, List[int]] = {}
    
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
        self.post_user_map, self.user_post_counts, self.user_list = self.data_access.load_user_data()
        
        # タグデータの読み込み
        self._load_tags_data()
        
        # タグインデックスの構築
        self._build_tag_index()
        
        # 初期化完了フラグ
        self.initialized = True
    
    def _load_vectors(self, source_dir: str) -> Tuple[List[int], Any]:
        """
        指定されたディレクトリからベクトルデータを読み込む
        
        Args:
            source_dir: ベクトルデータのディレクトリパス
            
        Returns:
            (post_ids, vectors)のタプル
        """
        import torch
        import safetensors.torch
        
        # ディレクトリパスを解決
        if source_dir == "embeddings":
            vector_dir = self.embeddings_dir
        else:
            vector_dir = self.embeddings_dir.parent / source_dir
        
        # meta.jsonの存在チェック
        meta_path = vector_dir / "meta.json"
        if not meta_path.exists():
            return [], torch.tensor([])
        
        # メタデータを読み込み
        import json
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return [], torch.tensor([])
        
        all_post_ids = []
        all_vectors = []
        
        # チャンク数を取得
        chunks = metadata.get("chunks", 0)
        
        # 存在するファイルのリストを作成
        existing_files = []
        for chunk_id in range(chunks):
            chunk_file = vector_dir / f"{chunk_id:04d}.safetensors"
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
    
    def _load_all_vectors(self) -> None:
        """全てのベクトルデータを読み込む"""
        # contentベクトルの読み込み（既存の動作を維持）
        self.post_ids, self.content_vectors = self._load_vectors("embeddings")
        
        # reasoningベクトルの読み込み
        _, self.reasoning_vectors = self._load_vectors("batch/reasoning")
        
        # summaryベクトルの読み込み
        _, self.summary_vectors = self._load_vectors("batch/summary")
        
        # 既存の動作を維持するため、vectorsをcontent_vectorsと同じものを指す
        self.vectors = self.content_vectors
    
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
    
    def _get_available_modes(self) -> List[str]:
        """
        利用可能なベクトル検索モードを取得
        
        Returns:
            利用可能なモードのリスト
        """
        available_modes = []
        
        # 単一ソースモード
        if self.content_vectors is not None and len(self.content_vectors) > 0:
            available_modes.append("content")
        if self.reasoning_vectors is not None and len(self.reasoning_vectors) > 0:
            available_modes.append("reasoning")
        if self.summary_vectors is not None and len(self.summary_vectors) > 0:
            available_modes.append("summary")
        
        # 統合モード（2つ以上のベクトルが必要）
        if len(available_modes) >= 2:
            available_modes.extend(["average", "product", "weighted"])
        
        return available_modes
    
    def _validate_search_mode(self, mode: str) -> None:
        """
        指定されたモードが利用可能かチェック
        
        Args:
            mode: 検索モード
            
        Raises:
            ValueError: モードが利用できない場合
        """
        available_modes = self._get_available_modes()
        
        if mode not in available_modes:
            raise ValueError(f"Vector search mode '{mode}' is not available. Available modes: {available_modes}")
    
    def _calculate_similarities(self, query_vector: Any, mode: str, weights: List[float] = None) -> Any:
        """
        指定されたモードでクエリベクトルとの類似度を計算
        
        Args:
            query_vector: クエリベクトル
            mode: 検索モード
            weights: 重み付けモード用の重み（合計1.0）
            
        Returns:
            類似度テンソル
        """
        import torch
        import torch.nn.functional as F
        
        # 単一ソースモード
        if mode == "content":
            return F.cosine_similarity(self.content_vectors, query_vector, dim=1)
        elif mode == "reasoning":
            return F.cosine_similarity(self.reasoning_vectors, query_vector, dim=1)
        elif mode == "summary":
            return F.cosine_similarity(self.summary_vectors, query_vector, dim=1)
        
        # 統合モード
        elif mode in ["average", "product", "weighted"]:
            similarities = []
            
            # 各ベクトルとの類似度を計算
            if self.content_vectors is not None and len(self.content_vectors) > 0:
                similarities.append(F.cosine_similarity(self.content_vectors, query_vector, dim=1))
            if self.reasoning_vectors is not None and len(self.reasoning_vectors) > 0:
                similarities.append(F.cosine_similarity(self.reasoning_vectors, query_vector, dim=1))
            if self.summary_vectors is not None and len(self.summary_vectors) > 0:
                similarities.append(F.cosine_similarity(self.summary_vectors, query_vector, dim=1))
            
            if len(similarities) == 0:
                return torch.tensor([])
            
            # 統合方法に応じて計算
            if mode == "average":
                return torch.stack(similarities).mean(dim=0)
            elif mode == "product":
                result = similarities[0]
                for sim in similarities[1:]:
                    result = result * sim
                return result
            elif mode == "weighted":
                if weights is None:
                    # デフォルトの重み（内容重視）
                    weights = [0.7, 0.2, 0.1]
                
                # 重みを正規化
                weights = weights[:len(similarities)]
                weight_sum = sum(weights)
                if weight_sum > 0:
                    weights = [w / weight_sum for w in weights]
                
                weighted_sims = [sim * weight for sim, weight in zip(similarities, weights)]
                return torch.stack(weighted_sims).sum(dim=0)
        
        raise ValueError(f"Unknown mode: {mode}")
    
    def _convert_mode_to_source(self, mode: str) -> str:
        """
        ベクトル検索モードをテキスト検索ソースに変換
        
        Args:
            mode: ベクトル検索モード
            
        Returns:
            テキスト検索ソース
            
        Raises:
            ValueError: ハイブリッドモードが指定された場合
        """
        # 単一ソースモードはそのままテキスト検索ソースに変換可能
        if mode in ["content", "reasoning", "summary"]:
            return mode
        
        # ハイブリッドモードはテキスト検索では不可能
        elif mode in ["average", "product", "weighted"]:
            raise ValueError(f"Hybrid mode '{mode}' is not supported for text search. Use vector search instead.")
        
        else:
            raise ValueError(f"Unknown mode: {mode}")
    
    def vector_search(self, query: str, top_k: int = None, mode: str = "content", weights: List[float] = None) -> List[Tuple[int, float]]:
        """
        ベクトル検索を実行
        
        Args:
            query: クエリ文字列（V|T形式対応）
            top_k: 取得件数制限
            mode: 検索モード ("content", "reasoning", "summary", "average", "product", "weighted")
            weights: 重み付けモード用の重み（合計1.0）
            
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
            self._load_all_vectors()
        
        # モードの妥当性チェック
        self._validate_search_mode(mode)
        
        # 類似度の計算
        similarities = self._calculate_similarities(query_vector, mode, weights)
        
        if similarities is None or len(similarities) == 0:
            return []
        
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
    
    def _generate_text_results(self, text_filter: str, source: str = "content") -> Generator[Tuple[dict, float], None, None]:
        """
        テキスト検索結果を(post_info, similarity)形式で生成
        
        Args:
            text_filter: テキストフィルタリング条件
            source: テキスト検索ソース
            
        Yields:
            (post_info, similarity)のタプル
        """
        text_results = self.search_posts_by_text(text_filter, limit=10000, source=source)
        for result in text_results:
            # タグ情報は既にsearch_posts_by_textで付加済み
            yield result, 1.0
    
    def _enrich_post_info(self, post_info: dict) -> dict:
        """
        タグ情報でpost_infoを拡張
        
        Args:
            post_info: 投稿情報辞書
            
        Returns:
            タグ情報が付加されたpost_info
        """
        post_id = post_info.get('post_id')
        if post_id and post_id in self.tags_data:
            post_info.update(self.tags_data[post_id])
        return post_info
    
    def _generate_vector_results(self, query: str, mode: str = "content", weights: List[float] = None) -> Generator[Tuple[dict, float], None, None]:
        """
        ベクトル検索結果を(post_info, similarity)形式で生成
        
        Args:
            query: クエリ文字列（V|T形式対応）
            mode: 検索モード
            weights: 重み付けモード用の重み
            
        Yields:
            (post_info, similarity)のタプル
        """
        all_results = self.vector_search(query, top_k=None, mode=mode, weights=weights)
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
            
            # タグ情報を付加
            post_info = self._enrich_post_info(post_info)
            
            yield post_info, similarity
    
    def search_similar(self, query: str, search_settings: SearchSettings, mode: str = "content", weights: List[float] = None) -> List[Tuple[int, float, dict]]:
        """
        類似検索を実行（フィルタリング付き）
        
        Args:
            query: クエリ文字列（V|T形式対応）
            search_settings: 検索設定
            mode: 検索モード ("content", "reasoning", "summary", "average", "product", "weighted")
            weights: 重み付けモード用の重み（合計1.0）
            
        Returns:
            (rank, similarity, post_info)のタプルリスト
        """
        # V|T検索の解析
        vector_query, text_filter = parse_pipeline_query(query)
        
        # 結果ジェネレーターの選択
        if not vector_query:
            if not text_filter:
                raise ValueError("Empty query: both vector and text parts are empty")
            # テキスト検索の場合、モードをソースに変換
            text_source = self._convert_mode_to_source(mode)
            results_generator = self._generate_text_results(text_filter, text_source)
        else:
            results_generator = self._generate_vector_results(query, mode, weights)
        
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
            
            # タグ情報を付加
            post_info = self._enrich_post_info(post_info)
            
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
    
    def _get_search_text(self, post_id: int, source: str) -> str:
        """
        指定されたソースからテキストを取得
        
        Args:
            post_id: 投稿ID
            source: 検索対象ソース ("content", "reasoning", "summary")
            
        Returns:
            検索対象テキスト
        """
        if source == "content":
            return self.data_access.posts_data.get(post_id, {}).get("content", "")
        
        elif source in ["reasoning", "summary"]:
            if post_id not in self.tags_data:
                return ""
            
            if source == "reasoning":
                return self.tags_data[post_id]["reasoning"]
            elif source == "summary":
                return self.tags_data[post_id]["summary"]
        
        return ""
    
    def search_posts_by_text(self, search_term: str, limit: int = 50, source: str = "content") -> List[dict]:
        """
        テキスト検索を実行
        
        Args:
            search_term: 検索語
            limit: 取得する最大件数
            source: 検索対象ソース ("content", "reasoning", "summary")
            
        Returns:
            検索結果リスト
        """
        # 検索語をパース
        include_terms, exclude_terms = parse_search_terms(search_term)
        
        # 結果を構築
        results = []
        for post_id, post_data in self.data_access.posts_data.items():
            # ソースに応じたテキストを取得
            search_text = self._get_search_text(post_id, source)
            
            if self.is_text_match(search_text, include_terms, exclude_terms):
                user = self.post_user_map.get(post_id, "")
                result = {
                    "post_id": post_id,
                    "content": post_data.get("content", ""),
                    "timestamp": post_data.get("timestamp", ""),
                    "url": post_data.get("url", ""),
                    "user": user
                }
                
                # タグ情報を付加
                if post_id in self.tags_data:
                    result.update(self.tags_data[post_id])
                
                results.append(result)
        
        # 新しい順でソート
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return results[:limit]
    
    def suggest_users(self, user_list: List[str]) -> Dict[str, List[str]]:
        """
        ユーザーのリストを受け取って存在しないユーザーに対してレーベンシュタイン距離で類似ユーザーを提案
        
        Args:
            user_list: チェック対象のユーザー名リスト
            
        Returns:
            存在しないユーザー名をキーとし、類似ユーザー上位5人をリストとする辞書
        """
        import Levenshtein
        
        # 存在しないユーザーを特定
        missing_users = [user for user in user_list if user not in self.user_post_counts]
        
        result = {}
        
        for missing_user in missing_users:
            # 全ユーザーとのレーベンシュタイン類似度を計算
            similarities = []
            for existing_user in self.user_list:
                ratio = Levenshtein.ratio(missing_user, existing_user)
                similarities.append((existing_user, ratio))
            
            # 類似度の降順でソート
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # 上位5人を抽出
            top_5 = [user for user, _ in similarities[:5]]
            result[missing_user] = top_5
        
        return result
    
    def _load_tags_data(self) -> None:
        """batch/results.jsonlが存在すれば読み込む"""
        results_path = self.embeddings_dir.parent / "batch" / "results.jsonl"
        if not results_path.exists():
            return
        
        import json
        try:
            with open(results_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    data = json.loads(line)
                    post_id = data["key"]
                    self.tags_data[post_id] = {
                        "reasoning": data["reasoning"],
                        "summary": data["summary"],
                        "tags": data["tags"]
                    }
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: タグデータの読み込みに失敗しました: {e}")
    
    def _build_tag_index(self) -> None:
        """タグから投稿IDへの逆引きインデックスを構築"""
        self.tag_index = {}
        
        for post_id, tag_data in self.tags_data.items():
            tags = tag_data.get("tags", [])
            for tag in tags:
                if tag not in self.tag_index:
                    self.tag_index[tag] = []
                self.tag_index[tag].append(post_id)
