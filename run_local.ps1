Invoke-RestMethod -Uri "http://127.0.0.1:8081/diff" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"file1":"file1.json", "file2":"file2.json"}' `
  | Select-Object -ExpandProperty diff `
  | ConvertTo-Json -Depth 10