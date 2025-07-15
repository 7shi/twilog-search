#!/usr/bin/env python3
"""
ベクトルストア - post_idをキーとしてベクトルを管理
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class VectorStore:
    """post_idをキーとしてベクトルを管理するクラス"""
    
    def __init__(self, vector_dir: str):
        """
        初期化（メタデータのみ読み込み）
        
        Args:
            vector_dir: ベクトルデータのディレクトリパス
        """
        self.vector_dir = Path(vector_dir)
        self.metadata = self._load_metadata()
        
        # ベクトルデータ（遅延読み込み）
        self.vectors = None
        self.post_id_to_index: Dict[int, int] = {}
        self.post_ids: List[int] = []
        self.loaded = False
    
    def _load_metadata(self) -> dict:
        """メタデータファイルを読み込む"""
        meta_path = self.vector_dir / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"メタデータファイルが見つかりません: {meta_path}")
        
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            raise RuntimeError(f"メタデータファイルの読み込みに失敗しました: {e}")
    
    def load_vectors(self) -> None:
        """実際のベクトル読み込み"""
        if self.loaded:
            return
        
        import torch
        import safetensors.torch
        
        all_post_ids = []
        all_vectors = []
        
        # チャンク数を取得
        chunks = self.metadata.get("chunks", 0)
        
        # 各チャンクファイルを読み込み
        for chunk_id in range(chunks):
            chunk_file = self.vector_dir / f"{chunk_id:04d}.safetensors"
            if chunk_file.exists():
                data = safetensors.torch.load_file(chunk_file)
                post_ids = data["post_ids"].tolist()
                vectors = data["vectors"]
                
                all_post_ids.extend(post_ids)
                all_vectors.append(vectors)
        
        # 全ベクトルを結合
        if all_vectors:
            self.vectors = torch.cat(all_vectors, dim=0)
            self.post_ids = all_post_ids
            
            # post_id → indexのマッピングを構築
            self.post_id_to_index = {post_id: idx for idx, post_id in enumerate(self.post_ids)}
            
            self.loaded = True
        else:
            raise RuntimeError(f"ベクトルファイルが見つかりません: {self.vector_dir}")
    
    def get_vector(self, post_id: int) -> Optional['torch.Tensor']:
        """
        post_idを渡すとベクトルを返す
        
        Args:
            post_id: 投稿ID
            
        Returns:
            ベクトル（見つからない場合はNone）
        """
        if not self.loaded:
            self.load_vectors()
        
        index = self.post_id_to_index.get(post_id)
        if index is None:
            return None
        
        return self.vectors[index]
    
    def vector_search(self, query_vector: 'torch.Tensor') -> List[Tuple[int, float]]:
        """
        ベクトルを渡すとコサイン類似度を計算して、類似度の降順で(post_id, similarity)のタプルリストを返す
        
        Args:
            query_vector: クエリベクトル
            
        Returns:
            (post_id, similarity)のタプルリスト（類似度降順）
        """
        import torch.nn.functional as F
        
        if not self.loaded:
            self.load_vectors()
        
        if self.vectors is None or len(self.vectors) == 0:
            return []
        
        # 次元を調整（必要に応じて）
        if query_vector.dim() == 2 and query_vector.shape[0] == 1:
            query_vector = query_vector.squeeze(0)
        
        # コサイン類似度を計算
        similarities = F.cosine_similarity(self.vectors, query_vector, dim=1)
        
        # 類似度でソート（降順）
        import torch
        sorted_indices = torch.argsort(similarities, descending=True)
        
        # 結果を作成
        results = []
        for idx in sorted_indices:
            post_id = self.post_ids[idx.item()]
            similarity = similarities[idx].item()
            results.append((post_id, similarity))
        
        return results
