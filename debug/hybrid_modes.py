#!/usr/bin/env python3
"""
ハイブリッド検索モードのテストスクリプト
"""

import sys
import asyncio
from pathlib import Path

# srcパスを追加
sys.path.append('src')

from twilog_server import TwilogServer

class HybridModesTester:
    """ハイブリッドモードテスト用クラス"""
    
    def __init__(self, embeddings_dir: str = "embeddings"):
        self.embeddings_dir = Path(embeddings_dir)
        self.server = None
    
    async def init_server(self):
        """TwilogServerを初期化"""
        print("Twilog Server 初期化中...")
        reasoning_dir = str(self.embeddings_dir.parent / "batch" / "reasoning")
        summary_dir = str(self.embeddings_dir.parent / "batch" / "summary")
        self.server = TwilogServer(str(self.embeddings_dir), reasoning_dir, summary_dir)
        await self.server.init_model()
        print("Twilog Server 初期化完了")
    
    async def test_hybrid_modes(self, query: str = "プログラミング", top_k: int = 5):
        """ハイブリッドモードのテスト"""
        print(f"\n=== ハイブリッドモードテスト (query: {query}, top_k: {top_k}) ===")
        
        search_engine = self.server.search_engine
        
        # テスト対象のモード
        test_modes = ["average", "maximum", "minimum"]
        
        for mode in test_modes:
            print(f"\n【{mode}モード】")
            try:
                results = search_engine.vector_search(query, mode=mode, top_k=top_k)
                print(f"  ✅ 成功: {len(results)}件の結果")
                
                if results:
                    for i, (post_id, similarity) in enumerate(results, 1):
                        print(f"    {i}. post_id: {post_id}, score: {similarity:.6f}")
                else:
                    print("    結果なし")
                    
            except Exception as e:
                print(f"  ❌ エラー: {e}")
                import traceback
                print(f"  トレースバック:")
                for line in traceback.format_exc().split("\n"):
                    if line.strip():
                        print(f"    {line}")
                        
        # averageモードで重み付きテスト
        print(f"\n【averageモード（重み付き）】weights=[0.7, 0.2, 0.1]")
        try:
            results = search_engine.vector_search(query, mode="average", top_k=top_k, weights=[0.7, 0.2, 0.1])
            print(f"  ✅ 成功: {len(results)}件の結果")
            
            if results:
                for i, (post_id, similarity) in enumerate(results, 1):
                    print(f"    {i}. post_id: {post_id}, score: {similarity:.6f}")
            else:
                print("    結果なし")
                
        except Exception as e:
            print(f"  ❌ エラー: {e}")

async def main():
    """メイン関数"""
    print("=== ハイブリッド検索モードテストスクリプト ===")
    
    # テスターを初期化
    tester = HybridModesTester()
    
    # サーバー初期化
    await tester.init_server()
    
    # ハイブリッドモードテスト
    await tester.test_hybrid_modes()

if __name__ == "__main__":
    asyncio.run(main())