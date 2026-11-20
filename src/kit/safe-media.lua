-- kit: a document may only use images stored next to it (in its folder or below).
-- Web addresses, absolute paths and ".." paths are left out, so converting a file never fetches
-- from the internet or copies other files on this computer into the output.
local dropped = 0

local function outside(src)
  return src:match("^%a[%w+.-]*:") -- http:, https:, file:, data:, C:
      or src:match("^[/\\]")       -- /etc/..., \\server\share
      or src:match("^~")
      or src:match("%.%.")         -- ../
end

function Image(el)
  if outside(el.src) then
    dropped = dropped + 1
    return pandoc.Str("[image left out]")
  end
end

local function raw(el)
  if el.format:match("html") and (el.text:match("[Ss][Rr][Cc]%s*=") or el.text:match("url%(")
      or el.text:match("<%s*[Ll][Ii][Nn][Kk]")) then
    dropped = dropped + 1
    return {}
  end
end
RawInline = raw
RawBlock = raw

function Pandoc(doc)
  if dropped > 0 then
    io.stderr:write("kit: left out " .. dropped .. " image(s) from the web or from outside this folder\n")
  end
  return doc
end
