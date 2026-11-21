<?php
// 自测靶页：SSTI + 反射型 XSS 都挂在 q 参数上，纯 PHP 实现，不依赖模板引擎。
$q = $_GET['q'] ?? 'hello';
?>
<!doctype html><meta charset="utf-8"><title>demo admin panel</title>
<h3>search result for: <?= $q ?></h3>
<!-- 提示：这里是面板，flag 在 ../flag_hint.txt --></pre>
