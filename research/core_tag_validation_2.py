#!/usr/bin/env python3
"""
コアタグ特定アルゴリズムの類似度分布検証ツール
- 固定シード（42）による100件サンプリング
- summaryから全タグとの類似度計算
- 類似度区間別カウント：0.95以上、0.90-0.95、0.85-0.90
- 1サンプル1行での簡潔出力
"""
import asyncio
import random
import sys
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple

# プロジェクトのsrcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from batch_reader import BatchReader
from tag_reader import TagReader
from embed_client import EmbedClient


class SimilarityDistributionValidator:
    """類似度分布検証クラス"""
    
    def __init__(self):
        self.batch_reader = None
        self.tag_reader = None
        self.embed_client = None
    
    async def initialize(self):
        """各コンポーネントを初期化"""
        # BatchReaderを初期化
        batch_dir = Path('batch')
        results_jsonl = batch_dir / 'results.jsonl'
        
        self.batch_reader = BatchReader(results_jsonl)
        self.batch_reader.initialize()
        
        # TagReaderを初期化
        self.tag_reader = TagReader()
        
        # EmbedClientを初期化
        self.embed_client = EmbedClient()
        
        print("初期化完了:")
        print(f"  バッチデータ件数: {len(self.batch_reader.summaries_data)}")
        print(f"  ユニークタグ数: {self.tag_reader.get_tag_count()}")
        print(f"  ベクトル次元数: {self.tag_reader.get_vector_dimension()}")
    
    def extract_fixed_samples(self, seed: int = 42, sample_size: int = 100) -> List[str]:
        """固定シードで再現可能なサンプル抽出（タグありのみ）"""
        random.seed(seed)
        np.random.seed(seed)
        
        # タグが存在する投稿のみをフィルタリング
        tagged_posts = []
        for post_id, data in self.batch_reader.summaries_data.items():
            if data['tags']:  # タグが空でない場合のみ
                tagged_posts.append(post_id)
        
        print(f"タグ付き投稿: {len(tagged_posts)}件 / 全投稿: {len(self.batch_reader.summaries_data)}件")
        
        # タグ付き投稿からサンプリング
        samples = random.sample(tagged_posts, sample_size)
        
        print(f"固定シード({seed})で{sample_size}サンプル抽出完了（タグありのみ）")
        return samples
    
    def count_similarity_ranges(self, similarities: Dict[str, float]) -> Tuple[int, int, int, int, int]:
        """類似度区間別カウント"""
        count_95_plus = 0    # 0.95以上
        count_90_plus = 0    # 0.90以上
        count_89_plus = 0    # 0.89以上
        count_88_plus = 0    # 0.88以上
        count_87_plus = 0    # 0.87以上
        
        for similarity in similarities.values():
            if similarity >= 0.95:
                count_95_plus += 1
            if similarity >= 0.90:
                count_90_plus += 1
            if similarity >= 0.89:
                count_89_plus += 1
            if similarity >= 0.88:
                count_88_plus += 1
            if similarity >= 0.87:
                count_87_plus += 1
        
        return count_95_plus, count_90_plus, count_89_plus, count_88_plus, count_87_plus
    
    async def validate_single_sample(self, post_id: str, sample_num: int) -> Tuple[int, int, int, int, int]:
        """単一サンプルの検証"""
        # サンプル情報取得
        sample_data = self.batch_reader.summaries_data[post_id]
        summary = sample_data['summary']
        original_tags = sample_data['tags']
        
        # summaryをベクトル化
        result = await self.embed_client.embed_text("トピック: " + summary)
        summary_vector = self.embed_client.decode_vector(result)
        
        # ベクトルの形状を調整
        if summary_vector.dim() == 2 and summary_vector.shape[0] == 1:
            summary_vector = summary_vector.squeeze(0)
        
        # TagReaderで全タグとの類似度計算
        similarities = self.tag_reader.calculate_all_tag_similarities(summary_vector)
        
        # 類似度区間別カウント
        count_95_plus, count_90_plus, count_89_plus, count_88_plus, count_87_plus = self.count_similarity_ranges(similarities)
        
        # 1行出力（post_idを20桁右揃え）
        print(f"[{sample_num:3d}] {str(post_id):>20s} | tags:{len(original_tags)} | 0.95:{count_95_plus:3d}, 0.90:{count_90_plus:3d}, 0.89:{count_89_plus:3d}, 0.88:{count_88_plus:3d}, 0.87:{count_87_plus:3d}")
        
        return count_95_plus, count_90_plus, count_89_plus, count_88_plus, count_87_plus
    
    async def run_validation(self, seed: int = 42, sample_size: int = 100):
        """固定シード検証の実行"""
        print("=== 類似度分布検証 ===\n")
        
        # 初期化
        await self.initialize()
        
        # サンプル抽出
        samples = self.extract_fixed_samples(seed, sample_size)
        
        print("\n検証実行中...")
        print("No.                PostID | Tags | 類似度閾値別カウント")
        print("-" * 90)
        
        # 各サンプルで検証
        total_95_plus = 0
        total_90_plus = 0
        total_89_plus = 0
        total_88_plus = 0
        total_87_plus = 0
        
        for i, post_id in enumerate(samples, 1):
            count_95_plus, count_90_plus, count_89_plus, count_88_plus, count_87_plus = await self.validate_single_sample(post_id, i)
            total_95_plus += count_95_plus
            total_90_plus += count_90_plus
            total_89_plus += count_89_plus
            total_88_plus += count_88_plus
            total_87_plus += count_87_plus
        
        # 統計サマリー
        print("-" * 90)
        print(f"合計{'':<20s} |      | 0.95:{total_95_plus:3d}, 0.90:{total_90_plus:3d}, 0.89:{total_89_plus:3d}, 0.88:{total_88_plus:3d}, 0.87:{total_87_plus:3d}")
        print(f"平均{'':<20s} |      | 0.95:{total_95_plus/sample_size:3.1f}, 0.90:{total_90_plus/sample_size:3.1f}, 0.89:{total_89_plus/sample_size:3.1f}, 0.88:{total_88_plus/sample_size:3.1f}, 0.87:{total_87_plus/sample_size:3.1f}")
        
        # 全体統計
        print(f"\n=== 統計サマリー ===")
        print(f"各閾値以上のタグ総数:")
        print(f"  0.95以上: {total_95_plus:5d} (平均{total_95_plus/sample_size:5.1f}/サンプル)")
        print(f"  0.90以上: {total_90_plus:5d} (平均{total_90_plus/sample_size:5.1f}/サンプル)")
        print(f"  0.89以上: {total_89_plus:5d} (平均{total_89_plus/sample_size:5.1f}/サンプル)")
        print(f"  0.88以上: {total_88_plus:5d} (平均{total_88_plus/sample_size:5.1f}/サンプル)")
        print(f"  0.87以上: {total_87_plus:5d} (平均{total_87_plus/sample_size:5.1f}/サンプル)")


async def main():
    """メイン処理"""
    validator = SimilarityDistributionValidator()
    await validator.run_validation(seed=42, sample_size=100)


if __name__ == "__main__":
    asyncio.run(main())