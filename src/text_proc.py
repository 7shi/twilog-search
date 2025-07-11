#!/usr/bin/env python3
"""
テキスト処理ユーティリティ
"""
from typing import List, Tuple


def parse_search_terms(text: str) -> Tuple[List[str], List[str]]:
    """
    シェル風のルールで検索語をパースする
    
    Args:
        text: パース対象の文字列
        
    Returns:
        (include_terms, exclude_terms)のタプル
        include_terms: 含む条件の検索語リスト
        exclude_terms: 除外条件の検索語リスト
    """
    include_terms = []
    exclude_terms = []
    
    i = 0
    while i < len(text):
        # 空白をスキップ
        while i < len(text) and text[i].isspace():
            i += 1
        
        if i >= len(text):
            break
        
        # 除外フラグ
        is_exclude = False
        if text[i] == '-':
            is_exclude = True
            i += 1
        
        # termを抽出
        term = ""
        quoted = False
        
        while i < len(text):
            char = text[i]
            
            if char == '\\' and i + 1 < len(text):
                # エスケープ処理
                i += 1
                term += text[i]
                i += 1
            elif char == '"' and not quoted:
                # クォート開始
                quoted = True
                i += 1
            elif char == '"' and quoted:
                # クォート終了
                quoted = False
                i += 1
                break
            elif char.isspace() and not quoted:
                # 区切り文字（クォート外）
                break
            else:
                term += char
                i += 1
        
        # termが空でない場合のみ追加
        if term:
            if is_exclude:
                exclude_terms.append(term)
            else:
                include_terms.append(term)
    
    return include_terms, exclude_terms


def test_parse_search_terms():
    """テスト関数"""
    test_cases = {
        "基本的なスペース区切り": [
            ("hello world", (["hello", "world"], [])),
        ],
        
        "ダブルクォート処理": [
            ('"hello world" test', (["hello world", "test"], [])),
            ('"quoted"', (["quoted"], [])),
            ('"quoted" normal', (["quoted", "normal"], [])),
        ],
        
        "除外条件": [
            ("hello -world", (["hello"], ["world"])),
            ("-", ([], [])),
        ],
        
        "エスケープ処理": [
            (r'hello \-world', (["hello", "-world"], [])),
            (r'"hello \"test\" world"', (["hello \"test\" world"], [])),
            (r'test \"escaped\" normal', (["test", "\"escaped\"", "normal"], [])),
            (r"\-", (["-"], [])),
        ],
        
        "複雑な組み合わせ": [
            ('apple "banana cake" -orange -"grape juice" \\\\backslash', 
             (["apple", "banana cake", "\\backslash"], ["orange", "grape juice"])),
        ],
        
        "空文字列と空白のみ": [
            ("", ([], [])),
            ("   ", ([], [])),
        ],
        
        "先頭・末尾の空白": [
            ("  hello world  ", (["hello", "world"], [])),
        ],
        
        "連続する空白": [
            ("hello    world", (["hello", "world"], [])),
        ],
    }
    
    print("=== parse_search_terms テスト ===")
    print()
    
    for category, cases in test_cases.items():
        print(f"【{category}】")
        for input_text, expected in cases:
            print(f"  入力: {repr(input_text)}")
            result = parse_search_terms(input_text)
            
            if result == expected:
                print(f"  ✓ 成功: {result}")
            else:
                print(f"  ✗ 失敗:")
                print(f"    期待値: {expected}")
                print(f"    実際値: {result}")
            print()
    
    print("=== 仕様説明 ===")
    print("1. スペースで区切られたtermを分離")
    print("2. ダブルクォート(\")で囲まれた部分は1つのtermとして扱う")
    print("3. バックスラッシュ(\\)でエスケープ処理")
    print("4. マイナス(-)で始まるtermは除外条件として扱う")
    print("5. マイナスを文字として使いたい場合は\\-でエスケープ")
    print("6. 戻り値: (include_terms, exclude_terms)のタプル")


if __name__ == "__main__":
    test_parse_search_terms()