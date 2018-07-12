# Ansibleを使ってシスコルータで繰り返しコマンドを実行する

ネットワーク機器では状態を確認するために繰り返しコマンドを打ち続ける場面があります。

たとえばシスコルータに乗り込んで1秒ごとに
```
show process cpu | include CPU
```
を打ち込んでCPU使用率をチェックしたい、という場面は時々でてきます。
こういうのはTeraTERMマクロの方が得意だと思いますが、それをAnsibleでやってみます。


<br>

# モジュールを作らないと実現できないこと

繰り返し実行という部分は、`include_tasks` と `loop` を使えばよさそうですが、
タスクからタスクへの切り替えに時間がかかってしまうため、短い間隔での繰り返しには向きません。

また、Ansibleはリアルタイムに情報を表示できませんので、代替策としてファイルへの書き出しで対応するしかありません。

こういうのは独自のモジュールを作ってなんとかするしかないのですが、
幸いAnsibleのモジュール作りはさほど難しくありません。

実際にモジュールを作ってやってみた結果。


# モジュール

./libraryにモジュールを配置します。


# 使い方

１秒間隔で１０回、コマンドを送り込みます。
画面には表示されませんので、`log/{{ inventory_hostname }}.log` に書かれる内容を `tail -f` して確認します。

```
---
#
# Ciscoルータにコマンドを打ち込みます
#
# 2018/07/10 初版
#
# Takamitsu IIDA (@takamitsu-iida)

- name: execute command on cisco devices
  hosts: 11f_routers
  gather_facts: False

  # 同時実行数
  serial: 100

  vars:
    #  - include: vars/exec_commands.yml
    exec_commands:
      - "show process cpu | in CPU"
      - "ping 172.18.0.1"

  tasks:
    - name: run exec commands on remote nodes
      repeat_ios_cmd:
        commands: "{{ exec_commands }}"
        sleep: 1
        repeat: 10
        store_stdout: false
        logdir: ./log
        logfile: "{{ inventory_hostname }}.log"
      register: r
```


# 止め方

ctrl-cで止めちゃえばいいのですが、任意のタイミングできれいに停止させたいなら、非同期処理を使うといいでしょう。

```
---
#
# Ciscoルータにコマンドを打ち込みます
#
# 2018/07/10 初版
#
# Takamitsu IIDA (@takamitsu-iida)

- name: execute command on cisco devices
  hosts: 11f_routers
  gather_facts: False

  # 同時実行数
  serial: 100

  vars:
    #  - include: vars/exec_commands.yml
    exec_commands:
      - "show process cpu | in CPU"
      - "ping 172.18.0.1"

  tasks:
    - name: run exec commands on remote nodes
      repeat_ios_cmd:
        commands: "{{ exec_commands }}"
        sleep: 1
        repeat: 10
        store_stdout: false
        logdir: ./log
        logfile: "{{ inventory_hostname }}.log"
      register: r
      # 注意！
      # 非同期にした場合、ctrl-cでプレイブックを止めるとタスクがバックグランドで走りっぱなしになってしまう
      # ctrl-cで処理を強制終了したいなら非同期にはしないこと
      async: 43200  # 60min*60sec*12 = 12 hour
      poll: 0

    #
    # 非同期で実行した場合、中断するかどうかをユーザに問い合わせる
    #
    - name: user input
      local_action:
        module: pause
        prompt: "yで処理を中止し、それ以外は終わるまでポーリングします"
      register: yn

    - name: check async status
      async_status:
        jid: "{{ r.ansible_job_id }}"
      register: job_status

    - name: stop if user input
      fail:
        msg: "ユーザ入力により中断しました。failedと表示されますがエラーではありません。"
      #failed_when: False
      when:
        - yn.user_input == 'y'
        - job_status.finished != true
      run_once: true

    - name: wait for end of async job
      async_status:
        jid: "{{ r.ansible_job_id }}"
      register: job_status
      until: job_status.finished
      retries: 43200  # 60min*60sec*12 = 12 hour

    - debug:
        var: job_status
```

このプレイブックを実行すると、このように聞かれますので、yを入力すればその時点で止まります。

```
TASK [user input] **************************************************************
[user input]
yで処理を中止し、それ以外は終わるまでポーリングします:
ok: [r1 -> localhost]
```

