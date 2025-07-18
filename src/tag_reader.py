#!/usr/bin/env python3
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class TagReader:
    """タグデータ（TSV、TXT、safetensors）を統合的に読み込み・管理するクラス"""
    
    def __init__(self, batch_dir: str = 'batch', load_vectors: bool = True):
        """
        Args:
            batch_dir: batch/ディレクトリのパス
            load_vectors: safetensorsファイルを読み込むかどうか
        """
        self.batch_dir = Path(batch_dir)
        self.tags_tsv_path = self.batch_dir / 'tags.tsv'
        self.tags_txt_path = self.batch_dir / 'tags.txt'
        self.tags_safetensors_path = self.batch_dir / 'tags.safetensors'
        self.load_vectors = load_vectors
        
        # データ保持用
        self.tag_data: List[Dict] = []  # TSVデータ（post_id -> タグリスト）
        self.unique_tags: List[str] = []  # 重複なしタグリスト（tags.txtから）
        self.tag_to_index: Dict[str, int] = {}  # タグ名 -> インデックス のマッピング
        self.tag_vectors = None  # タグベクトル（torch.Tensor）
        
        self._load_data()
    
    def _load_data(self):
        """全データファイルを読み込み"""
        self._load_tsv()
        self._load_txt()
        if self.load_vectors:
            self._load_safetensors()
    
    def _load_tsv(self):
        """tags.tsvを読み込み"""
        if not self.tags_tsv_path.exists():
            print(f"警告: {self.tags_tsv_path} が見つかりません")
            return
        
        with open(self.tags_tsv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if not lines:
                return
            
            # ヘッダー行を解析
            header = lines[0].strip().split('\t')
            
            # データ行を処理
            for line in lines[1:]:
                if not line.strip():
                    continue
                
                fields = line.strip().split('\t')
                if len(fields) < 1:
                    continue
                
                post_id = fields[0]
                tags = []
                
                # post_id以外のフィールドからタグを抽出
                for i in range(1, len(fields)):
                    tag = fields[i].strip()
                    if tag:
                        tags.append(tag)
                
                self.tag_data.append({
                    'post_id': post_id,
                    'tags': tags
                })
    
    def _load_txt(self):
        """tags.txtを読み込み、インデックスマッピングを作成"""
        if not self.tags_txt_path.exists():
            print(f"警告: {self.tags_txt_path} が見つかりません")
            return
        
        with open(self.tags_txt_path, 'r', encoding='utf-8') as f:
            for index, line in enumerate(f):
                tag = line.strip()
                if tag:
                    self.unique_tags.append(tag)
                    self.tag_to_index[tag] = index
    
    def _load_safetensors(self):
        """tags.safetensorsを読み込み"""
        if not self.tags_safetensors_path.exists():
            print(f"警告: {self.tags_safetensors_path} が見つかりません")
            return
        
        try:
            # 遅延import
            import safetensors.torch
            tensors = safetensors.torch.load_file(self.tags_safetensors_path)
            self.tag_vectors = tensors['vectors']
        except Exception as e:
            print(f"エラー: tags.safetensorsの読み込みに失敗: {e}")
    
    def get_tag_vector(self, tag: str):
        """
        タグ名からベクトルを取得
        
        Args:
            tag: タグ名
            
        Returns:
            タグのベクトル（torch.Tensor）、見つからない場合はNone
        """
        if tag not in self.tag_to_index:
            return None
        
        if self.tag_vectors is None:
            return None
        
        index = self.tag_to_index[tag]
        return self.tag_vectors[index]
    
    def get_tags_for_post(self, post_id: str) -> List[str]:
        """
        投稿IDからタグリストを取得
        
        Args:
            post_id: 投稿ID
            
        Returns:
            タグのリスト
        """
        for entry in self.tag_data:
            if entry['post_id'] == post_id:
                return entry['tags']
        return []
    
    def get_posts_with_tag(self, tag: str) -> List[str]:
        """
        特定のタグを持つ投稿IDのリストを取得
        
        Args:
            tag: タグ名
            
        Returns:
            投稿IDのリスト
        """
        posts = []
        for entry in self.tag_data:
            if tag in entry['tags']:
                posts.append(entry['post_id'])
        return posts
    
    def get_all_tags(self) -> List[str]:
        """全ユニークタグのリストを取得"""
        return self.unique_tags.copy()
    
    def get_tag_count(self) -> int:
        """ユニークタグ数を取得"""
        return len(self.unique_tags)
    
    def search_similar_tags(self, query_vector, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        クエリベクトルと類似するタグを検索
        
        Args:
            query_vector: 検索クエリのベクトル（torch.Tensor）
            top_k: 上位何件を返すか
            
        Returns:
            (タグ名, 類似度スコア) のタプルのリスト
        """
        if self.tag_vectors is None:
            return []
        
        # 遅延import
        import torch
        
        # コサイン類似度を計算
        similarities = torch.nn.functional.cosine_similarity(
            query_vector.unsqueeze(0), 
            self.tag_vectors, 
            dim=1
        )
        
        # 上位k件のインデックスを取得
        top_k = min(top_k, len(self.unique_tags))
        top_similarities, top_indices = torch.topk(similarities, top_k)
        
        results = []
        for i in range(top_k):
            idx = top_indices[i].item()
            score = top_similarities[i].item()
            tag = self.unique_tags[idx]
            results.append((tag, score))
        
        return results
    
    def get_vector_dimension(self) -> Optional[int]:
        """ベクトルの次元数を取得"""
        if self.tag_vectors is None:
            return None
        return self.tag_vectors.shape[1]  # 第2次元を取得
    
    def is_data_loaded(self) -> Dict[str, bool]:
        """各データファイルの読み込み状況を取得"""
        return {
            'tsv': len(self.tag_data) > 0,
            'txt': len(self.unique_tags) > 0,
            'safetensors': self.tag_vectors is not None
        }


if __name__ == "__main__":
    # テスト実行
    reader = TagReader()
    
    # データ読み込み状況の確認
    status = reader.is_data_loaded()
    print(f"データ読み込み状況: {status}")
    
    if status['txt']:
        print(f"ユニークタグ数: {reader.get_tag_count()}")
        print(f"最初の10タグ: {reader.get_all_tags()[:10]}")
    
    if status['safetensors']:
        print(f"ベクトル次元数: {reader.get_vector_dimension()}")
        
        # 最初のタグのベクトルを取得してテスト
        if reader.unique_tags:
            first_tag = reader.unique_tags[0]
            vector = reader.get_tag_vector(first_tag)
            if vector is not None:
                print(f"タグ '{first_tag}' のベクトル形状: {vector.shape}")
    
    if status['tsv']:
        print(f"TSVデータ件数: {len(reader.tag_data)}")
        # 最初の数件の投稿のタグを表示
        for i, entry in enumerate(reader.tag_data[:3]):
            print(f"投稿ID {entry['post_id']}: {entry['tags']}")