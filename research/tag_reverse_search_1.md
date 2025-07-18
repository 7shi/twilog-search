# tag_reverse_search_1

## なぜこの実装が存在するか

### タグベース検索スコアリング手法の定量評価必要性
**Problem**: PLAN.mdで設計されたタグベース検索システムにおいて、投稿が持つ複数タグの類似度を単一スコアに統合する手法（mean, median, max, q75, top_k, weighted）が複数存在したが、どの手法が最も効果的かを定量的に評価する仕組みがなかった。

**Solution**: summaryをクエリとして逆引き検索を行い、元投稿のランキング位置で各手法の性能を測定する検証システムを実装。6つの手法を固定シード検証で比較し、統計的根拠に基づく最適手法選択を可能にした。

### top_k制限による処理時間短縮の採用
**Problem**: 38,898個の全タグとの類似度計算は処理負荷が高く、実用性を考慮した効率化が必要と考えられた。

**Solution**: `search_similar_tags(top_k=1000)`を使用し、上位1000タグのみに制限することで処理時間短縮を図った。これにより全タグの97%を除外し、計算効率を向上させる方針を採用。

### 固定シード検証による再現性確保
**Problem**: ランダムサンプリングによる検証では、実行ごとに結果が変動し、手法間の性能比較が不安定になる問題があった。

**Solution**: シード値42による決定的サンプリングを採用し、10サンプルでの統計的分析により再現可能な検証結果を実現。タグ付き投稿のみを対象とすることで、検証の妥当性を確保した。

### 6手法包括比較による最適解探索
**Problem**: 単一の統計量（平均値のみ等）では、タグの多様性や外れ値の影響を適切に処理できない可能性があり、どの統計的手法が検索精度に最も寄与するかが不明であった。

**Solution**: 基本統計量（mean, median, max）、分位数ベース（q75）、上位重視手法（top_k, weighted）の6つを包括的に比較し、平均順位・中央値順位・Top10/20/100率による多角的評価を実施した。