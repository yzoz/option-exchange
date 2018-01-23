<!doctype html>
<html>
	<head>
		<title>{{title}}</title>
		<link rel="stylesheet" href="" />
		<style>
			body{font-size:0.75em}
		</style>
	</head>
	<body>
		<header>
			<div id="menu">
				{{price}} / {{realised}} / {{clearTotal}}
			</div>
		</header>
		<article>
<%
for balance in balances:
trades =  str(balance['trades']).replace('{', '<br />')
%>
User: {{balance['hash']}} | {{balance['seed']}}<br />
Own: {{balance['balance']['own']}}<br />
Orders: {{balance['balance']['orders']}}<br />
Contracts: {{balance['balance']['contracts']}}<br />
Prize: {{balance['balance']['prize']}}<br />
Realised: {{balance['balance']['realised']}}<br />
Available: {{balance['balance']['available']}}<br />
Clear: {{balance['clear']}}<br />
Trades: {{!trades}}<br />
-------------------------<br />
%end
		</article>
		<footer>
			
		</footer>
	</body>
</html>