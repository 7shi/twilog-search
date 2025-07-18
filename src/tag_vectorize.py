#!/usr/bin/env python3
import asyncio
import safetensors.torch
import torch
from pathlib import Path
from typing import List
from tqdm import tqdm
from embed_client import EmbedClient
import argparse


async def main():
    """batch/tags.txtからタグを読み込み、ベクトル化してsafetensorsに出力"""
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='タグベクトル化スクリプト')
    parser.add_argument('--limit', type=int, help='処理するタグ数の上限（テスト用）')
    parser.add_argument('-o', '--output', type=str, default='batch/tags.safetensors', help='出力ファイルパス（デフォルト: batch/tags.safetensors）')
    args = parser.parse_args()
    
    # パス設定
    batch_dir = Path('batch')
    tags_txt_path = batch_dir / 'tags.txt'
    tags_safetensors_path = Path(args.output)
    
    if not tags_txt_path.exists():
        print(f"エラー: {tags_txt_path} が見つかりません")
        return
    
    # tags.txtからタグを読み込み
    print(f"タグを読み込み中: {tags_txt_path}")
    tags = []
    with open(tags_txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            tag = line.strip()
            if tag:
                tags.append(tag)
                # limitが指定されている場合は制限
                if args.limit and len(tags) >= args.limit:
                    break
    
    print(f"読み込み完了: {len(tags)}個のタグ")
    if args.limit:
        print(f"制限適用: 最初の{args.limit}個のタグのみ処理")
    
    # EmbedClientを使用してベクトル化
    client = EmbedClient()
    print("タグのベクトル化を開始...")
    
    vectors = []
    for tag in tqdm(tags, desc="ベクトル化中"):
        # embed_textでベクトル化（Ruri v3のprefix付き）
        result = await client.embed_text("トピック: " + tag)
        
        # decode_vectorでtensorを取得
        vector = client.decode_vector(result)
        vectors.append(vector)
    
    print("ベクトル化完了")
    
    # ベクトルをsafetensorsに保存
    print(f"ベクトルを保存中: {tags_safetensors_path}")
    stacked_vectors = torch.stack(vectors)
    
    # 形状を確認・最適化（2次元に正規化）
    print(f"ベクトル形状: {stacked_vectors.shape}")
    if len(stacked_vectors.shape) == 3 and stacked_vectors.shape[1] == 1:
        stacked_vectors = stacked_vectors.squeeze(1)
        print(f"形状を最適化: {stacked_vectors.shape}")
    
    tensors = {'vectors': stacked_vectors}
    safetensors.torch.save_file(tensors, tags_safetensors_path)
    
    print(f"完了: {len(tags)}個のタグベクトルを保存しました")
    print(f"ファイル: {tags_safetensors_path}")
    print(f"最終形状: {stacked_vectors.shape}")


if __name__ == "__main__":
    asyncio.run(main())