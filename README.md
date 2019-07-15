# wiortc-mpy-sample
Wio Extension - RTC 用の MicroPython サンプルスクリプト

## 内容

* boot.py -- ブート時実行スクリプト
* wiolte.py -- wiolte　モジュール(*1)
* wiortc.py -- wiortc モジュール
* main.py -- wiortc を使ったサンプルスクリプト
* uasyncio/ -- 非同期 I/O モジュール(*2)。

(*1) 以下の github リポジトリにある wiolte.py を使っています。

```
https://github.com/ciniml/mpy-wiolte
```

(*2) 以下の micropython-lib　にある uasyncio を使っています。

```
https://github.com/micropython/micropython-lib
```
 
## 必要なもの

* Wio LTE JP version
* Wio Wio Extension - RTC
* Grove のブザー
* 電源(2A供給可能で自動 OFF 機能のないモバイルバッテリーなど)

## 事前準備

### Wio LTE 用 MicroPython ファームウェアのインストール

井田 健太さんが Wio LTE 用に MicroPython を移植してくれています。
コンパイル済みのファームウェアのバイナリは以下から入手できます。

```
https://www.fugafuga.org/wiolte/mpy_wio_lte.zip
```

1. PC に上記 zip ファイルをダウンロードして展開する
2. Wio LTE と PC を USB ケーブルにつないで DFU モードにする(BOOTボタンを押しながら RST ボタンを押す)
3. dfu-util コマンド(*3)で firmware.dfu を Wio LTE に書き込む

```
$ dfu-util –alt 0 –download firmware.dfu
```

4. 書き込みが完了したら RST ボタンを押す

(*3) dfu-util コマンドは以下のように導入します。

* Windows用

以下からバイナリをダウンロードして、dfu-util-static.exe を dfu-util.exe に改名して使います。

```
http://dfu-util.sourceforge.net/releases/dfu-util-0.8-binaries/win32-mingw32/dfu-util-static.exe
```

* Ubuntu用

以下でインストールします。

```
$ sudo apt install dfu-util
```

* macOS用

事前に Homebrew (https://brew.sh/index_ja)の環境を設定して、以下でインストールします。

```
$ brew install
```

## サンプルスクリプトの動かし方

1. Wio LTE を PC につなぐと USB ストレージとしてマウントされるので、そこに本リポジトリのスクリプトすべてをコピーします
2. Wio LTE の USB ストレージをアンマウントした後、PC から取り外して Wio Extension - RTC を I2C につなぎ、Grove のブザーを D38 につなぎます
3. Wio Extension - RTC の USB (J4)から Wio LTE の電源へ USB ケーブルでつなぎます
4. Wio Extension - RTC の USB (J3)に 5V 電源を USB ケーブルでつなぎます
5. 30秒単位に Wio LTE の電源が入り、ブザーが鳴ります

## サンプルスクリプトについて

本サンプルスクリプトは、以下の公式の Arduino サンプルスケッチを MicroPython 用に移植したものです。

```
https://github.com/Seeed-Studio/Wio_Extension_RTC
```

## クラス wiortc.WioRTC

公式の Arduino サンプルスケッチにある WioRTC.{h,cpp} を参考に実装しています。

### コンストラクタ

WioRTC(wire=None)

	wire: pyb.I2C オブジェクトを指定。指定しない場合は内部で自動で作成

### メソッド

begin()

	Wio Extension - RTC を始動する。

set_wakeup_period(sec)

	sec 秒後に電源を入れるように指示する。

	実際のところ、255 秒より大きな値の場合には 60 秒単位の指定、15300 秒より大きな値の場合には  3600 秒単位の指定になります。

shutdown()

	電源の切断を指示する。

eeprom_write(address, data)

	EEPROM のアドレス address にバイト列 data を書き込む。

eeprom_read(address, data)

	EEPROM のアドレス address からバイト列 data に読み込む。
