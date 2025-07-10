# コマンドライン引数の解析
import argparse
parser = argparse.ArgumentParser(description='Twilogデータの読み込みと表示')
parser.add_argument('csv_path', nargs='?', default='twilog.csv', help='CSVファイルのパス (デフォルト: twilog.csv)')
args = parser.parse_args()

# CSVファイルを読み込み
import pandas as pd
df = pd.read_csv(args.csv_path, header=None)

# 列名を設定
df.columns = ['post_id', 'url', 'timestamp', 'content', 'log_type']

# ログタイプの意味: 1=ツイート, 2=いいね, 3=ブックマーク

# データの確認
print(f"データ行数: {len(df)}")
print(f"データ形状: {df.shape}")
print("\n最初の5行:")
print(df.head())

print("\n最後の5行:")
print(df.tail())

print("\n列の情報:")
print(df.info())
