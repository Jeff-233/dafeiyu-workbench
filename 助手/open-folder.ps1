$ErrorActionPreference = 'Continue'
$root  = Split-Path -Parent $MyInvocation.MyCommand.Path
$tokF  = Join-Path $root 'token.txt'
$logF  = Join-Path $root 'log.txt'
$port  = 18765
$token = ''
if (Test-Path -LiteralPath $tokF) { $token = (Get-Content -LiteralPath $tokF -Raw).Trim() }

function Say($m) {
  try { Add-Content -LiteralPath $logF -Value ((Get-Date).ToString('MM-dd HH:mm:ss') + '  ' + $m) -Encoding UTF8 } catch {}
}

if (-not $token) { Say 'token.txt missing'; exit 1 }

function Test-Alive {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', $port)
    $c.Close()
    return $true
  } catch { return $false }
}
if (Test-Alive) { Say 'already running, exit'; exit 0 }

$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $port)
$bound = $false
for ($i = 0; $i -lt 20; $i++) {
  try { $listener.Start(); $bound = $true; break }
  catch {
    if ($i -eq 0) { Say ('bind busy, retry: ' + $_.Exception.Message) }
    Start-Sleep -Milliseconds 600
  }
}
if (-not $bound) { Say ('bind failed after retries on port ' + $port); exit 1 }
Say ('listening 127.0.0.1:' + $port)

while ($true) {
  $client = $listener.AcceptTcpClient()
  try {
    $client.ReceiveTimeout = 4000
    $st  = $client.GetStream()
    $buf = New-Object byte[] 4096
    $sb  = New-Object System.Text.StringBuilder
    for ($i = 0; $i -lt 8; $i++) {
      $n = $st.Read($buf, 0, $buf.Length)
      if ($n -le 0) { break }
      [void]$sb.Append([System.Text.Encoding]::ASCII.GetString($buf, 0, $n))
      if ($sb.ToString().Contains(([char]13 + [char]10 + [char]13 + [char]10))) { break }
    }

    $sep  = [char]13 + [char]10
    $line = (($sb.ToString() -split $sep))[0]
    $body = '{"ok":false,"err":"bad request"}'
    $m = [regex]::Match($line, '^GET\s+(\S+)\s+HTTP')
    if ($m.Success) {
      $u    = $m.Groups[1].Value
      $qi   = $u.IndexOf('?')
      $path = if ($qi -ge 0) { $u.Substring(0, $qi) } else { $u }
      $q    = @{}
      if ($qi -ge 0) {
        foreach ($pair in $u.Substring($qi + 1).Split('&')) {
          if (-not $pair) { continue }
          $kv = $pair.Split('=', 2)
          $k  = [uri]::UnescapeDataString($kv[0])
          $v  = if ($kv.Length -gt 1) { [uri]::UnescapeDataString($kv[1].Replace('+', ' ')) } else { '' }
          $q[$k] = $v
        }
      }
      if ($path -eq '/ping') {
        $body = '{"ok":true,"msg":"pong"}'
      } elseif ($path -eq '/open') {
        if ($q['t'] -ne $token) {
          $body = '{"ok":false,"err":"bad token"}'
        } else {
          $p = $q['p']
          if ($p -and (Test-Path -LiteralPath $p)) {
            $d = [char]34
            if ($q['sel'] -eq '1') { Start-Process explorer.exe -ArgumentList ('/select,' + $d + $p + $d) }
            else { Start-Process explorer.exe -ArgumentList ($d + $p + $d) }
            $body = '{"ok":true}'
            Say ('open ' + $p)
          } else {
            $body = '{"ok":false,"err":"not found"}'
            Say ('miss ' + $p)
          }
        }
      } elseif ($path -eq '/pick') {
        if ($q['t'] -ne $token) {
          $body = '{"ok":false,"err":"bad token"}'
        } elseif ($q['dry'] -eq '1') {
          $body = '{"ok":true,"dry":true}'
        } else {
          try {
            Add-Type -AssemblyName System.Windows.Forms
            Add-Type -AssemblyName System.Drawing
            $dlg = New-Object System.Windows.Forms.OpenFileDialog
            $dlg.Title = '选一张图当工作台头图'
            $dlg.Filter = '图片|*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.ico|所有文件|*.*'
            $dlg.CheckFileExists = $true
            if ($q['src'] -and (Test-Path -LiteralPath $q['src'])) {
              $r = [System.Windows.Forms.DialogResult]::OK
              $pre = $q['src']
            } else {
              $r = $dlg.ShowDialog()
              $pre = ''
            }
            if ($r -ne [System.Windows.Forms.DialogResult]::OK) {
              $body = '{"ok":false,"err":"cancelled"}'
            } else {
              $src = if ($pre) { $pre } else { $dlg.FileName }
              $siteDir = Split-Path -Parent $root
              $thDir = Join-Path $siteDir 'thumbs'
              if (-not (Test-Path -LiteralPath $thDir)) { New-Item -ItemType Directory -Path $thDir -Force | Out-Null }
              $nm  = 'c_' + ([guid]::NewGuid().ToString('N').Substring(0,10)) + '.jpg'
              $dst = Join-Path $thDir $nm
              $img = [System.Drawing.Image]::FromFile($src)
              $w0 = $img.Width; $h0 = $img.Height
              $scale = 480.0 / [Math]::Max($w0, $h0)
              if ($scale -gt 1) { $scale = 1.0 }
              $w = [int][Math]::Max(1, [Math]::Round($w0 * $scale))
              $h = [int][Math]::Max(1, [Math]::Round($h0 * $scale))
              $bmp = New-Object System.Drawing.Bitmap($w, $h)
              $g = [System.Drawing.Graphics]::FromImage($bmp)
              $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
              $g.Clear([System.Drawing.Color]::White)
              $g.DrawImage($img, 0, 0, $w, $h)
              $g.Dispose()
              $bmp.Save($dst, [System.Drawing.Imaging.ImageFormat]::Jpeg)
              $bmp.Dispose()
              $img.Dispose()
              $safe = (Split-Path -Leaf $src).Replace('\', '\\').Replace('"', '\"')
              $body = '{"ok":true,"thumb":"thumbs/' + $nm + '","name":"' + $safe + '"}'
              Say ('pick ' + $src)
            }
          } catch {
            $body = '{"ok":false,"err":"pick failed"}'
            Say ('pick err ' + $_.Exception.Message)
          }
        }
      } elseif ($path -eq '/list') {
        if ($q['t'] -ne $token) {
          $body = '{"ok":false,"err":"bad token"}'
        } else {
          $p = $q['p']
          if (-not $p -or -not (Test-Path -LiteralPath $p -PathType Container)) {
            $body = '{"ok":false,"err":"not found"}'
          } else {
            try {
              $items = New-Object System.Collections.ArrayList
              $cnt = 0
              foreach ($f in (Get-ChildItem -LiteralPath $p -Force -ErrorAction SilentlyContinue)) {
                if ($cnt -ge 3000) { break }
                $isD = 0
                $sz = 0
                if ($f.PSIsContainer) { $isD = 1 } else { try { $sz = [long]$f.Length } catch {} }
                $mt = 0
                try { $mt = [long]([datetimeoffset]$f.LastWriteTime).ToUnixTimeSeconds() } catch {}
                [void]$items.Add([pscustomobject]@{ n = $f.Name; d = $isD; s = $sz; t = $mt })
                $cnt++
              }
              if ($items.Count -eq 0) { $body = '{"ok":true,"items":[]}' }
              else { $body = '{"ok":true,"items":' + (ConvertTo-Json -InputObject @($items) -Compress -Depth 3) + '}' }
            } catch {
              $body = '{"ok":false,"err":"list failed"}'
              Say ('list err ' + $_.Exception.Message)
            }
          }
        }
      } elseif ($path -eq '/rebuild') {
        if ($q['t'] -ne $token) {
          $body = '{"ok":false,"err":"bad token"}'
        } else {
          $runF = Join-Path $root 'runner.json'
          if (-not (Test-Path -LiteralPath $runF)) {
            $body = '{"ok":false,"err":"runner.json missing"}'
          } else {
            try {
              $rj = Get-Content -LiteralPath $runF -Raw -Encoding UTF8 | ConvertFrom-Json
              $sw = [System.Diagnostics.Stopwatch]::StartNew()
              $pr = Start-Process -FilePath $rj.py -ArgumentList ('"' + $rj.build + '"') -PassThru -Wait -WindowStyle Hidden
              $sw.Stop()
              $body = '{"ok":true,"code":' + $pr.ExitCode + ',"ms":' + $sw.ElapsedMilliseconds + '}'
              Say ('rebuild ' + $sw.ElapsedMilliseconds + 'ms code ' + $pr.ExitCode)
            } catch {
              $body = '{"ok":false,"err":"rebuild failed"}'
              Say ('rebuild err ' + $_.Exception.Message)
            }
          }
        }
      } else {
        $body = '{"ok":false,"err":"no route"}'
      }
    }

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    $cr = [char]13 + [char]10
    $head = 'HTTP/1.1 200 OK' + $cr +
            'Content-Type: application/json; charset=utf-8' + $cr +
            'Access-Control-Allow-Origin: *' + $cr +
            'Content-Length: ' + $bytes.Length + $cr +
            'Connection: close' + $cr + $cr
    $hb = [System.Text.Encoding]::ASCII.GetBytes($head)
    $st.Write($hb, 0, $hb.Length)
    $st.Write($bytes, 0, $bytes.Length)
    $st.Flush()
  } catch {
    Say ('err ' + $_.Exception.Message)
  } finally {
    try { $client.Close() } catch {}
  }
}
