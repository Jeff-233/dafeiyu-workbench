# -*- coding: utf-8 -*-
"""把一堆本地目录（folders.json）生成为一张可视化工作台 index.html。

用法：
    python build_workbench.py           # 生成 index.html
    python build_workbench.py --apply   # 顺带把剪贴板里的页面补丁并进 folders.json（「更新工作台.bat」走这个）

依赖：Python 3.9+、Pillow（pip install pillow）
"""
import json, os, hashlib, sys, uuid, shutil
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = HERE                     # 仓库目录本身就是站点目录
THUMB_DIR = os.path.join(OUT_DIR, "thumbs")
AIDE_DIR = os.path.join(OUT_DIR, "助手")
HELPER_PORT = 18765                # 小助手端口，改了要同步改 助手\open-folder.ps1 与 停止助手.bat
MAX_PER = 240          # 每个图库最多收录多少张
THUMB_PX = 320
TREE_THUMB_PER_CARD = 2000  # 文件浏览器里每个入口最多给多少张图做缩略图
TREE_THUMB_CAP = 9000       # 全局上限
CONF = os.path.join(OUT_DIR, "folders.json")
SAMPLE = os.path.join(OUT_DIR, "folders.sample.json")
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".jfif", ".avif", ".heic"}



def win(p):
    return p.replace("/", "\\")


def helper_token():
    """小助手的口令：存在 助手\\token.txt，页面里嵌同一个，防止别的网页乱调。"""
    try:
        os.makedirs(AIDE_DIR, exist_ok=True)
        p = os.path.join(AIDE_DIR, "token.txt")
        if os.path.exists(p):
            t = open(p, encoding="utf-8").read().strip()
            if t:
                return t
        t = uuid.uuid4().hex
        with open(p, "w", encoding="utf-8") as f:
            f.write(t)
        return t
    except Exception as e:
        print("  小助手口令写入失败：", e)
        return ""


def load_conf():
    if not os.path.exists(CONF) and os.path.exists(SAMPLE):
        try:
            shutil.copyfile(SAMPLE, CONF)
            print("  首次运行：已按 folders.sample.json 生成 folders.json，记得改成你自己的目录")
        except Exception as e:
            print("  复制示例配置失败：", e)
    if not os.path.exists(CONF):
        return {"groups": [], "add": [], "trash": []}
    try:
        with open(CONF, encoding="utf-8-sig") as f:
            c = json.load(f)
    except Exception as e:
        print("folders.json 读不了，先按空的来：", e)
        return {"groups": [], "add": [], "trash": []}
    return {"groups": c.get("groups") or [],
            "add": c.get("add") or [],
            "trash": c.get("trash") or []}


def save_conf(c):
    with open(CONF, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)


def load_groups(conf):
    """把 folders.json 的 groups 读成 [(组名, 组拼音, [(名字, 路径, 拼音, 图库key)])] + 颜色表"""
    groups, colors = [], {}
    for g in conf.get("groups") or []:
        title = (g.get("name") or "").strip() or "未命名"
        items = []
        for c in g.get("cards") or []:
            name = (c.get("name") or "").strip()
            path = (c.get("path") or "").strip()
            if not name or not path:
                continue
            items.append((name, path.replace("\\", "/"), c.get("py") or "", c.get("gallery") or ""))
        col = (g.get("color") or "").strip()
        if col:
            colors[title] = col
        groups.append((title, g.get("py") or "", items))
    return groups, colors


def scan_dir(path):
    p = win(path)
    if not os.path.isdir(p):
        return 0, False
    try:
        return len(os.listdir(p)), True
    except Exception:
        return 0, True


def list_images(path, limit):
    root = win(path)
    if not os.path.isdir(root):
        return []
    found = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in IMG_EXT:
                fp = os.path.join(dp, fn)
                try:
                    found.append((os.path.getmtime(fp), fp))
                except OSError:
                    pass
    found.sort(key=lambda x: x[0], reverse=True)
    return [fp for _, fp in found[:limit]]


def read_clipboard():
    try:
        import subprocess
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, timeout=20)
        return out.stdout.decode("utf-8", "ignore")
    except Exception as e:
        print("读剪贴板失败：", e)
        return ""


def apply_clipboard():
    """更新工作台.bat 会带 --apply：把剪贴板里的 {add:[...], trash:[...]} 并进 folders.json"""
    if "--apply" not in sys.argv:
        return
    raw = read_clipboard().strip()
    if not raw.startswith("{"):
        print("剪贴板里没有 JSON 补丁，跳过。")
        return
    try:
        patch = json.loads(raw)
    except Exception as e:
        print("剪贴板内容不是合法 JSON，跳过：", e)
        return
    if not patch.get("_wb"):
        print("剪贴板里不是工作台的补丁（缺 _wb 标记），跳过。")
        return
    conf = load_conf()
    added = 0
    for a in patch.get("add") or []:
        name, path = (a.get("name") or "").strip(), (a.get("path") or "").strip().replace("\\", "/")
        if not name or not path:
            continue
        conf["add"] = [x for x in conf["add"]
                       if win(x.get("path") or "") != win(path) or (x.get("name") or "") != name]
        conf["add"].append({"group": (a.get("group") or "自 定 义").strip() or "自 定 义",
                            "name": name, "path": path,
                            "py": a.get("py") or "", "gallery": a.get("gallery") or ""})
        added += 1
    if "trash" in patch:
        conf["trash"] = [t.replace("\\", "/") for t in (patch.get("trash") or [])]
    save_conf(conf)
    print("补丁已应用：新增 %d 项，垃圾箱 %d 项" % (added, len(conf["trash"])))
    try:
        import subprocess
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Set-Clipboard -Value 'workbench patch applied'"],
                       capture_output=True, timeout=20)
    except Exception:
        pass

# ---------------------------------------------------------------- 目录数据
# (组名, 拼音, [(名字, 路径, 拼音, 图库key或"")])
GROUPS = []  # 实际分组从 folders.json 读，见 load_groups()

COLORS = ["#5fb0e8", "#e8a05f", "#b57fe8", "#5fd6a8", "#e8725f", "#8899aa"]


def file_url(p):
    p = p.replace("\\", "/")
    drive = p[0]
    rest = p[2:].lstrip("/")
    return "file:///" + drive + ":/" + "/".join(quote(s) for s in rest.split("/"))


SYLLABLES = set("""
a ai an ang ao ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
ca cai can cang cao ce cen ceng cha chai chan chang chao che chen cheng chi chong chou
chu chua chuai chuan chuang chui chun chuo ci cong cou cu cuan cui cun cuo
da dai dan dang dao de dei deng di dia dian diao die ding diu dong dou du duan dui dun duo
e ei en eng er fa fan fang fei fen feng fo fou fu
ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui gun guo
ha hai han hang hao he hei hen heng hong hou hu hua huai huan huang hui hun huo
ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun
ka kai kan kang kao ke ken keng kong kou ku kua kuai kuan kuang kui kun kuo
la lai lan lang lao le lei leng li lia lian liang liao lie lin ling liu long lou lu
luan lue lun luo lv lve ma mai man mang mao me mei men meng mi mian miao mie min ming
miu mo mou mu na nai nan nang nao ne nei nen neng ni nian niang niao nie nin ning niu
nong nou nu nuan nue nuo nv nve o ou pa pai pan pang pao pei pen peng pi pian piao pie
pin ping po pou pu qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun
ran rang rao re ren reng ri rong rou ru ruan rui run ruo
sa sai san sang sao se sen seng sha shai shan shang shao she shei shen sheng shi shou
shu shua shuai shuan shuang shui shun shuo si song sou su suan sui sun suo
ta tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun tuo
wa wai wan wang wei wen weng wo wu xi xia xian xiang xiao xie xin xing xiong xiu xu
xuan xue xun ya yan yang yao ye yi yin ying yong you yu yuan yue yun
za zai zan zang zao ze zei zen zeng zha zhai zhan zhang zhao zhe zhei zhen zheng zhi
zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo zi zong zou zu zuan zui zun zuo
""".split())


CHARS = {
    "平": "ping", "面": "mian", "设": "she", "计": "ji", "近": "jin", "期": "qi",
    "参": "can", "材": "cai", "质": "zhi", "学": "xue", "素": "su", "库": "ku",
    "字": "zi", "体": "ti", "绘": "hui", "画": "hua", "南": "nan", "岛": "dao",
    "社": "she", "实": "shi", "习": "xi", "工": "gong", "作": "zuo", "桌": "zhuo",
    "游": "you", "企": "qi", "划": "hua", "创": "chuang", "视": "shi", "频": "pin",
    "制": "zhi", "摄": "she", "影": "ying", "书": "shu", "籍": "ji", "音": "yin",
    "乐": "yue", "跑": "pao", "团": "tuan", "直": "zhi", "播": "bo", "动": "dong",
    "巡": "xun", "礼": "li", "总": "zong", "目": "mu", "录": "lu", "电": "dian",
    "定": "ding", "收": "shou", "藏": "cang", "集": "ji", "照": "zhao", "片": "pian",
    "转": "zhuan", "手": "shou", "机": "ji", "原": "yuan", "暂": "zan", "存": "cun",
    "剪": "jian", "辑": "ji", "课": "ke", "程": "cheng", "下": "xia", "载": "zai",
    "版": "ban", "戏": "xi", "启": "qi", "独": "du", "立": "li", "办": "ban",
    "公": "gong", "软": "ruan", "件": "jian", "功": "gong", "能": "neng", "具": "ju",
    "器": "qi", "文": "wen", "档": "dang", "生": "sheng", "活": "huo", "子": "zi",
    "画": "hua", "风": "feng", "格": "ge", "宝": "bao", "图": "tu", "考": "kao",
    "屏": "ping", "中": "zhong",
}


def initials(name):
    out = []
    for ch in name:
        if ch in CHARS:
            out.append(CHARS[ch][0])
        elif ch.isascii() and ch.isalnum():
            out.append(ch.lower())
    return "".join(out)


def collect_tree(root, max_depth=3, cap=3000):
    """把目录树收成 [name, isDir, size, mtime, children?]，深度受限、条目有上限。"""
    budget = [cap]

    def walk(d, depth):
        try:
            es = list(os.scandir(d))
        except Exception:
            return []
        es.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
        out = []
        for e in es:
            if budget[0] <= 0:
                break
            budget[0] -= 1
            try:
                isdir = e.is_dir()
                st = e.stat()
            except Exception:
                continue
            node = [e.name, 1 if isdir else 0, 0 if isdir else st.st_size, int(st.st_mtime)]
            if isdir and depth < max_depth:
                sub = walk(e.path, depth + 1)
                if sub:
                    node.append(sub)
            out.append(node)
        return out

    return walk(root, 1)


def tree_images(root, nodes, out, limit):
    """把树里所有图片文件的绝对路径收集出来（深度优先，最多 limit 张）。"""
    for n in nodes:
        if len(out) >= limit:
            return
        p = os.path.join(root, n[0])
        if n[1]:
            if len(n) > 4:
                tree_images(p, n[4], out, limit)
        elif os.path.splitext(n[0])[1].lower() in IMG_EXT:
            out.append((p, n[3]))


def newest_image(root, nodes, limit):
    """树里最新的那张图，用来做卡片封面（封面跟着最近干的活走，比「第一张」有信号）。"""
    got = []
    tree_images(root, nodes, got, limit)
    if not got:
        return None
    got.sort(key=lambda x: -x[1])
    return got[0][0]


SKIP_EXT = {".lnk", ".ini", ".db", ".tmp", ".log", ".dat", ".sys", ".dll", ".exe"}

# 「最近动过的文件」只认内容类文件，不然会被游戏/软件配置刷屏（.vdf .acf .json .bak…）
CONTENT_EXT = IMG_EXT | {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv",
    ".psd", ".psb", ".ai", ".eps", ".indd", ".cdr", ".sketch", ".fig", ".xmind", ".mind",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".mp4", ".mov", ".mkv", ".avi", ".flv", ".wmv", ".webm",
    ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg",
    ".epub", ".mobi", ".ttf", ".otf", ".blend", ".c4d", ".ma", ".mb",
    ".clip", ".procreate", ".sai", ".kra", ".ase", ".abr", ".afdesign", ".aep", ".prproj",
}


def tree_files(root, nodes, out, limit, card_name):
    """收集树里的文件（非目录），带修改时间。给「最近动过的文件」用。"""
    for n in nodes:
        if len(out) >= limit:
            return
        p = os.path.join(root, n[0])
        if n[1]:
            if len(n) > 4:
                tree_files(p, n[4], out, limit, card_name)
        else:
            ext = os.path.splitext(n[0])[1].lower()
            if ext not in CONTENT_EXT or n[0].startswith("~$") or n[0].startswith("."):
                continue
            out.append((n[3], os.path.abspath(p), n[0], card_name))


def main():
    apply_clipboard()
    conf = load_conf()
    trash = {win(t) for t in conf["trash"]}

    GROUPS, GCOLOR = load_groups(conf)
    groups = [[t, gpy, list(items)] for t, gpy, items in GROUPS]
    if not groups:
        print("folders.json 里还没有 groups，请参照 folders.sample.json 填一份。")
        return
    for a in conf["add"]:
        name = (a.get("name") or "").strip()
        path = (a.get("path") or "").strip()
        if not name or not path:
            continue
        path = path.replace("\\", "/")
        item = (name, path, a.get("py") or "", a.get("gallery") or "")
        g = (a.get("group") or "自 定 义").strip() or "自 定 义"
        for grp in groups:
            if grp[0] == g:
                grp[2].append(item)
                break
        else:
            groups.append([g, "", [item]])

    os.makedirs(THUMB_DIR, exist_ok=True)
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    def make_thumb(src):
        """返回 ("thumbs/xx.jpg", 是否新建)；失败返回 (None, False)。"""
        name = hashlib.sha1(src.encode("utf-8")).hexdigest()[:16] + ".jpg"
        dst = os.path.join(THUMB_DIR, name)
        if os.path.exists(dst):
            return "thumbs/" + name, False
        try:
            with Image.open(src) as im:
                im = im.convert("RGB")
                im.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
                im.save(dst, "JPEG", quality=80, optimize=True)
            return "thumbs/" + name, True
        except Exception:
            return None, False

    gkeys, gpath = [], {}
    for title, gpy, items in groups:
        for name, path, py, gal in items:
            if gal and gal not in gkeys:
                gkeys.append(gal)
                gpath[gal] = path

    manifest = {}
    for key in gkeys:
        paths = list_images(gpath[key], MAX_PER)
        out, made = [], 0
        for src in paths:
            th, new = make_thumb(src)
            if not th:
                continue
            made += 1 if new else 0
            out.append([th, file_url(os.path.abspath(src)), os.path.basename(src)])
        if out:
            manifest[key] = out
        print("  图库 %-10s 收录 %4d 张，新建缩略图 %d" % (key, len(out), made))

    groups_js = []
    trees = {}
    card_meta = []          # (row, path, gal, exists)
    for i, (title, gpy, items) in enumerate(groups):
        rows = []
        for name, path, py, gal in items:
            count, exists = scan_dir(path)
            row = [name, path, py, count, exists,
                   gal if manifest.get(gal) else "", initials(name), ""]
            if win(path) in trash:
                continue
            rows.append(row)
            card_meta.append((row, path, gal, exists))
            if exists:
                trees[win(path)] = collect_tree(path.replace("/", os.sep))
        groups_js.append([title, gpy, (GCOLOR.get(title) or COLORS[i % len(COLORS)]), rows])

    tree_thumbs = {}
    tb_made = 0
    for key, tree in trees.items():
        if len(tree_thumbs) >= TREE_THUMB_CAP:
            break
        root = key.replace("\\", "/").replace("/", os.sep)
        imgs = []
        tree_images(root, tree, imgs, TREE_THUMB_PER_CARD)
        for src, _mt in imgs:
            if len(tree_thumbs) >= TREE_THUMB_CAP:
                break
            k = win(os.path.abspath(src))
            if k in tree_thumbs:
                continue
            th, new = make_thumb(src)
            if th:
                tree_thumbs[k] = th
                tb_made += 1 if new else 0
    print("  文件浏览器缩略图 %d 张，新建 %d 张" % (len(tree_thumbs), tb_made))

    # ---- 卡片封面：图库卡用最新一张，其余用目录里第一张有缩略图的 ----
    for row, path, gal, exists in card_meta:
        cov = ""
        if gal and manifest.get(gal):
            cov = manifest[gal][0][0]
        elif exists:
            tree = trees.get(win(path))
            if tree:
                got = []
                tree_images(path.replace("/", os.sep), tree, got, 40)
                got.sort(key=lambda x: -x[1])
                for src, _mt in got:
                    k = win(os.path.abspath(src))
                    if k in tree_thumbs:
                        cov = tree_thumbs[k]
                        break
        row[7] = cov

    # ---- 最近动过的文件：从已经扫好的树里挑 mtime 最新的 ----
    pool = []
    for row, path, gal, exists in card_meta:
        if not exists:
            continue
        tree = trees.get(win(path))
        if not tree:
            continue
        got = []
        tree_files(path.replace("/", os.sep), tree, got, 20, row[0])
        pool.extend(got)
    pool.sort(key=lambda x: -x[0])
    recent = []
    seen = set()
    for mt, absp, nm, cat in pool:
        if absp.lower() in seen:
            continue
        seen.add(absp.lower())
        recent.append([nm, file_url(absp), tree_thumbs.get(win(absp), ""), mt, cat, win(absp)])
        if len(recent) >= 12:
            break
    print("  最近动过的文件 %d 个" % len(recent))

    html = TEMPLATE.replace("__GROUPS__", json.dumps(groups_js, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__MANIFEST__", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__THUMBMAP__", json.dumps(tree_thumbs, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__TREE__", json.dumps(trees, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__RECENT__", json.dumps(recent, ensure_ascii=False, separators=(",", ":")))
    cfg = {"port": HELPER_PORT, "token": helper_token()}
    html = html.replace("__HELPER__", json.dumps(cfg, separators=(",", ":")))
    dst = os.path.join(OUT_DIR, "index.html")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)
    # 告诉本地小助手「怎么重建自己」：/rebuild 路由会读这个文件
    os.makedirs(AIDE_DIR, exist_ok=True)
    with open(os.path.join(AIDE_DIR, "runner.json"), "w", encoding="utf-8") as f:
        json.dump({"py": sys.executable,
                   "build": os.path.abspath(__file__)}, f, ensure_ascii=False)
    print("写入", dst, os.path.getsize(dst), "字节")


TEMPLATE = open(os.path.join(HERE, "workbench_template.html"), encoding="utf-8").read()

if __name__ == "__main__":
    main()
