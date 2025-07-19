#!/usr/bin/env python3
"""
要約ベクトル検索による原文反映性検証スクリプト

LLMによって生成された要約が埋め込みモデルから見て原文を適切に反映しているかを検証する。
要約をベクトル検索して、100位以内に元の投稿が現れるかを測定する。
"""
import asyncio
import sys
import random
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from batch_reader import BatchReader
from twilog_client import TwilogClient
from settings import SearchSettings


class SummaryVectorValidator:
    """要約ベクトル検索による原文反映性検証クラス"""
    
    def __init__(self, batch_file: Path, websocket_url: str = "ws://localhost:8765"):
        """
        初期化
        
        Args:
            batch_file: batch/results.jsonlファイルのパス
            websocket_url: WebSocketサーバーのURL
        """
        self.batch_reader = BatchReader(batch_file)
        self.client = TwilogClient(websocket_url)
        
    def extract_fixed_samples(self, seed: int, sample_size: int) -> List[int]:
        """固定シードで再現可能なサンプル抽出（要約ありのみ）"""
        random.seed(seed)
        
        # 要約データがある投稿のみをフィルタリング
        summaries_with_data = []
        for post_id, data in self.batch_reader.summaries_data.items():
            if data.get("summary", "").strip():  # 要約が空でない場合のみ
                summaries_with_data.append(post_id)
        
        print(f"要約あり投稿: {len(summaries_with_data):,}件 / 全投稿: {len(self.batch_reader.summaries_data):,}件")
        
        # 要約あり投稿からサンプリング
        actual_sample_size = min(sample_size, len(summaries_with_data))
        samples = random.sample(summaries_with_data, actual_sample_size)
        
        print(f"固定シード({seed})で{actual_sample_size}サンプル抽出完了（要約ありのみ）")
        return samples

    async def validate_summary_vector_search(self, sample_size: int, seed: int, mode: str = "content") -> Dict:
        """
        要約ベクトル検索による原文反映性を検証
        
        Args:
            sample_size: 検証サンプル数
            seed: ランダムシード（再現性確保）
            mode: 検索モード（content, reasoning, summary）
            
        Returns:
            検証結果の統計情報
        """
        print(f"🔍 要約ベクトル検索による原文反映性検証を開始")
        print(f"サンプル数: {sample_size}, シード: {seed}, モード: {mode}")
        
        # BatchReaderを初期化
        self.batch_reader.initialize()
        summaries_data = self.batch_reader.summaries_data
        
        if not summaries_data:
            raise ValueError("バッチ処理結果が読み込めませんでした")
        
        print(f"総要約データ数: {len(summaries_data):,}件")
        
        # 固定シードでサンプリング（tag_reverse_search_2.py参照）
        sampled_post_ids = self.extract_fixed_samples(seed, sample_size)
        actual_sample_size = len(sampled_post_ids)
        
        # 検証実行
        results = []
        hit_counts = {"top_10": 0, "top_20": 0, "top_50": 0, "top_100": 0}
        ranks = []
        
        for i, post_id in enumerate(sampled_post_ids, 1):
            summary = summaries_data[post_id]["summary"]
            print(f"\n[{i}/{actual_sample_size}] 投稿ID: {post_id}")
            print(f"要約: {summary[:100]}...")
            
            try:
                # 要約をクエリとしてベクトル検索（指定モード, top_k=100）
                search_result = await self.client.search_similar(
                    query_text=summary,
                    search_settings=SearchSettings(initial_top_k=100),
                    mode=mode
                )
                
                # 元投稿のランキングを確認
                rank = self._find_post_rank(search_result, post_id)
                
                if rank is not None:
                    ranks.append(rank)
                    print(f"✅ 元投稿が {rank}位 で発見")
                    
                    # ヒット率カウント
                    if rank <= 10:
                        hit_counts["top_10"] += 1
                    if rank <= 20:
                        hit_counts["top_20"] += 1
                    if rank <= 50:
                        hit_counts["top_50"] += 1
                    if rank <= 100:
                        hit_counts["top_100"] += 1
                else:
                    print("❌ 元投稿が100位以内に見つからず")
                
                results.append({
                    "post_id": post_id,
                    "summary": summary,
                    "rank": rank,
                    "found": rank is not None
                })
                
            except Exception as e:
                print(f"⚠️  検索エラー: {e}")
                results.append({
                    "post_id": post_id,
                    "summary": summary,
                    "rank": None,
                    "found": False,
                    "error": str(e)
                })
        
        # 統計計算
        stats = self._calculate_statistics(results, hit_counts, actual_sample_size)
        
        # 結果出力（サンプル詳細も表示）
        self._print_sample_details(sampled_post_ids, results, mode)
        self._print_results(stats)
        
        return {
            "statistics": stats,
            "detailed_results": results,
            "sample_size": actual_sample_size,
            "seed": seed
        }
    
    def _find_post_rank(self, search_results: List[Dict], target_post_id: int) -> Optional[int]:
        """
        検索結果から指定投稿のランキングを取得
        
        Args:
            search_results: 検索結果のリスト
            target_post_id: 対象投稿ID
            
        Returns:
            ランキング（1-based）、見つからない場合はNone
        """
        for rank, result in enumerate(search_results, 1):
            # 様々な可能性のあるキー構造に対応
            post_id = None
            if "post" in result and "post_id" in result["post"]:
                post_id = result["post"]["post_id"]
            elif "post" in result and "id" in result["post"]:
                post_id = result["post"]["id"]
            elif "id" in result:
                post_id = result["id"]
            elif "post_id" in result:
                post_id = result["post_id"]
            
            if post_id == target_post_id:
                return rank
        return None
    
    def _calculate_statistics(self, results: List[Dict], hit_counts: Dict[str, int], sample_size: int) -> Dict:
        """
        検証結果の統計を計算
        
        Args:
            results: 詳細結果のリスト
            hit_counts: ヒット数のカウント
            sample_size: サンプルサイズ
            
        Returns:
            統計情報の辞書
        """
        # 発見された投稿のランキングのみ抽出
        found_ranks = [r["rank"] for r in results if r["found"]]
        
        stats = {
            "total_samples": sample_size,
            "found_count": len(found_ranks),
            "not_found_count": sample_size - len(found_ranks),
            "found_rate": len(found_ranks) / sample_size * 100,
            "hit_rates": {
                "top_10": hit_counts["top_10"] / sample_size * 100,
                "top_20": hit_counts["top_20"] / sample_size * 100,
                "top_50": hit_counts["top_50"] / sample_size * 100,
                "top_100": hit_counts["top_100"] / sample_size * 100,
            }
        }
        
        if found_ranks:
            stats["rank_statistics"] = {
                "mean": np.mean(found_ranks),
                "median": np.median(found_ranks),
                "min": min(found_ranks),
                "max": max(found_ranks),
                "best_rank_count": sum(1 for r in found_ranks if r == 1)
            }
        
        return stats
    
    def _print_sample_details(self, sampled_post_ids: List[int], results: List[Dict], mode: str) -> None:
        """
        サンプル詳細を表示（tag_reverse_search_2.py形式）
        
        Args:
            sampled_post_ids: サンプル投稿IDのリスト
            results: 検証結果のリスト
        """
        print("\n" + "="*60)
        print(f"📋 サンプル詳細 ({len(sampled_post_ids)}件の固定シードサンプル)")
        print("="*60)
        
        print(f"\nサンプル別順位（要約ベクトル検索での元投稿ランキング, mode={mode}):")
        print(f"{'ID':<20s} {'順位':<8s} {'発見状況':<10s}")
        print("-" * 40)
        
        for i, (post_id, result) in enumerate(zip(sampled_post_ids, results)):
            rank_str = f"{result['rank']}位" if result['rank'] is not None else "圏外"
            found_str = "✅発見" if result['found'] else "❌圏外"
            print(f"{str(post_id):<20s} {rank_str:<8s} {found_str:<10s}")

    def _print_results(self, stats: Dict) -> None:
        """
        検証結果を出力
        
        Args:
            stats: 統計情報
        """
        print("\n" + "="*60)
        print("📊 要約ベクトル検索による原文反映性検証結果")
        print("="*60)
        
        print(f"総サンプル数: {stats['total_samples']:,}件")
        print(f"発見件数: {stats['found_count']:,}件")
        print(f"未発見件数: {stats['not_found_count']:,}件")
        print(f"発見率: {stats['found_rate']:.1f}%")
        
        print("\n🎯 ヒット率:")
        for key, rate in stats["hit_rates"].items():
            rank_range = key.replace("top_", "")
            print(f"  {rank_range}位以内: {rate:.1f}%")
        
        if "rank_statistics" in stats:
            rank_stats = stats["rank_statistics"]
            print("\n📈 ランキング統計 (発見された投稿のみ):")
            print(f"  平均順位: {rank_stats['mean']:.1f}位")
            print(f"  中央値順位: {rank_stats['median']:.1f}位")
            print(f"  最高順位: {rank_stats['min']}位")
            print(f"  最低順位: {rank_stats['max']}位")
            print(f"  1位獲得数: {rank_stats['best_rank_count']}件")
        
        print("\n💡 要約品質評価:")
        found_rate = stats['found_rate']
        top_10_rate = stats["hit_rates"]["top_10"]
        
        if found_rate >= 95:
            quality = "優秀"
            icon = "🟢"
        elif found_rate >= 85:
            quality = "良好"
            icon = "🟡"
        elif found_rate >= 70:
            quality = "普通"
            icon = "🟠"
        else:
            quality = "要改善"
            icon = "🔴"
        
        print(f"{icon} 要約品質: {quality}")
        print(f"  - 100位以内発見率: {found_rate:.1f}%")
        print(f"  - 10位以内高精度率: {top_10_rate:.1f}%")


async def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="要約ベクトル検索による原文反映性検証")
    parser.add_argument("-f", "--batch-file", type=Path, 
                       default=Path("batch/results.jsonl"),
                       help="バッチ処理結果ファイルのパス")
    parser.add_argument("-n", "--sample-size", type=int, default=50,
                       help="検証サンプル数 (デフォルト: 50)")
    parser.add_argument("-s", "--seed", type=int, default=42,
                       help="ランダムシード (デフォルト: 42)")
    parser.add_argument("-u", "--url", default="ws://localhost:8765",
                       help="WebSocketサーバーURL (デフォルト: ws://localhost:8765)")
    parser.add_argument("-m", "--mode", default="content",
                       choices=["content", "reasoning", "summary", "average", "maximum", "minimum"],
                       help="検索モード (デフォルト: content)")
    
    args = parser.parse_args()
    
    # ファイル存在確認
    if not args.batch_file.exists():
        print(f"❌ バッチファイルが見つかりません: {args.batch_file}")
        return 1
    
    try:
        validator = SummaryVectorValidator(args.batch_file, args.url)
        await validator.validate_summary_vector_search(args.sample_size, args.seed, args.mode)
        return 0
    except Exception as e:
        print(f"❌ 検証中にエラーが発生しました: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)