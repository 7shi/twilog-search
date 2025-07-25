# ハイブリッド検索モードテストスクリプト

## なぜこの実装が存在するか

### ハイブリッド検索モード検証の必要性
**Problem**: SearchEngineにproduct、harmonic、maximum、minimumモードを実装したが、これらの新機能が正常に動作するか確認する手段がなく、本格的なクライアントを使わずに軽量な検証が必要だった。

**Solution**: 独立したテストスクリプトを作成し、TwilogServerを直接初期化してSearchEngineのvector_searchメソッドを呼び出すシンプルなテスト環境を構築。各モードの動作確認と結果比較を効率的に実行できる構成とした。

### ハイブリッド検索モードの実用性検証
**Problem**: 実装したproductとharmonicモードがaverageモードとほぼ同じランキングを返すため、実用的価値が低く、コードの複雑性だけが増大していた。また、weightedモードが独立存在することでAPIの複雑性が増していた。

**Solution**: テストスクリプトによる実測データ収集を通じて、各モードの実用性を客観的に評価。検証結果に基づく最適化判断により、効率的な6モード構成を確立。詳細な検証データと最適化過程については[モード最適化レポート](../docs/20250716-mode-optimization.md)を参照。

### 軽量テスト環境の構築
**Problem**: twilog_client.pyを使った完全なテストは重く、ハイブリッドモードの単純な動作確認には過剰な機能が含まれていた。

**Solution**: TwilogServerを直接初期化し、SearchEngineのvector_searchメソッドのみを呼び出す最小限のテスト環境を構築。debug/ディレクトリ配置により、開発者向けツールとしての位置づけを明確化。